"""Unit tests for cmd_show_contract — the honesty-surface command."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from client.api import AssertenError
from client.cli import cmd_show_contract
from client.models import SessionState
from client.session import save_session


@pytest.fixture
def session(tmp_path, monkeypatch):
    sp = tmp_path / "session.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(sp))
    save_session(SessionState(
        backend_url="http://test",
        api_key="k",
        agent_id="a1",
        v0_version_id="v0id",
        v1_version_id="v1id",
        v2a_version_id="v2aid",
    ))
    return sp


class _StubClient:
    def __init__(self, *, contract=None, raises=None):
        self.contract = contract or {}
        self.raises = raises
        self.calls: list[tuple] = []

    def get_contract(self, agent_id, version_id):
        if self.raises is not None:
            raise self.raises
        self.calls.append((agent_id, version_id))
        return self.contract


def _patch_client(monkeypatch, stub):
    import client.cli
    monkeypatch.setattr(client.cli, "_client", lambda _state: stub)


def _contract_with(*, obligations=None, forbidden=None, tool_seqs=None):
    return {
        "id": "c1",
        "obligations": obligations or [],
        "forbidden_behaviors": forbidden or [],
        "tool_sequences": tool_seqs or [],
    }


# ── early guards ────────────────────────────────────────────────────────────


def test_show_contract_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(tmp_path / "s.json"))
    out = cmd_show_contract({})
    assert "No agent in session" in out


def test_show_contract_unknown_target(session, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_show_contract({"target": "v99"})
    assert "unknown target" in out


def test_show_contract_target_not_in_session(tmp_path, monkeypatch):
    sp = tmp_path / "s.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(sp))
    save_session(SessionState(backend_url="http://x", agent_id="a1"))  # no v1
    _patch_client(monkeypatch, _StubClient())
    out = cmd_show_contract({})  # default v1
    assert "no v1 in session" in out


def test_show_contract_404_friendly_message(session, monkeypatch):
    _patch_client(monkeypatch, _StubClient(
        raises=AssertenError(404, "not found", "http://test/contract")
    ))
    out = cmd_show_contract({})
    assert "No contract found" in out
    assert "asserten-prepare-eval" in out


# ── happy-path coverage table ───────────────────────────────────────────────


def test_show_contract_clean_coverage(session, monkeypatch):
    """LLM produced enough for every mandate — no injection callout."""
    contract = _contract_with(obligations=[
        {"id": "obl_1", "failure_category": "GOAL_COMPLETION", "text": "g1"},
        {"id": "obl_2", "failure_category": "GOAL_COMPLETION", "text": "g2"},
        {"id": "obl_3", "failure_category": "REASONING_QUALITY", "text": "r1"},
        {"id": "obl_4", "failure_category": "REASONING_QUALITY", "text": "r2"},
        {"id": "obl_5", "failure_category": "ESCALATION", "text": "e1"},
        {"id": "obl_6", "failure_category": "HALLUCINATION_GUARD", "text": "h1"},
    ])
    _patch_client(monkeypatch, _StubClient(contract=contract))

    out = cmd_show_contract({})

    assert "6 obligation(s)" in out
    assert "All obligations were produced by the LLM directly" in out
    # All four mandates marked OK
    assert "GOAL_COMPLETION" in out and "✓" in out
    assert "auto-injected" not in out.lower() or "_no auto-injected" in out.lower() or "no auto-injected placeholders" in out


def test_show_contract_with_injection_calls_out_per_category(session, monkeypatch):
    """REASONING_QUALITY came in below ≥2 — backend injected. Show that clearly."""
    contract = _contract_with(obligations=[
        {"id": "obl_1", "failure_category": "GOAL_COMPLETION", "text": "g1"},
        {"id": "obl_2", "failure_category": "GOAL_COMPLETION", "text": "g2"},
        {"id": "obl_3", "failure_category": "REASONING_QUALITY", "text": "LLM r1"},
        {"id": "obl_4", "failure_category": "REASONING_QUALITY",
         "text": "auto-injected placeholder", "auto_injected": True,
         "source": "auto_injected"},
        {"id": "obl_5", "failure_category": "ESCALATION", "text": "e1"},
        {"id": "obl_6", "failure_category": "HALLUCINATION_GUARD", "text": "h1"},
    ])
    _patch_client(monkeypatch, _StubClient(contract=contract))

    out = cmd_show_contract({})

    # 1 auto-injected entry called out clearly
    assert "1 obligation(s) were auto-injected" in out
    assert "Auto-injected entries" in out
    assert "obl_4" in out
    assert "REASONING_QUALITY" in out
    # Mandate-coverage table marks REASONING_QUALITY with 2 found, 1 injected
    assert "| REASONING_QUALITY |" in out


def test_show_contract_hallucination_guard_counted_from_forbidden(session, monkeypatch):
    """HALLUCINATION_GUARD can appear as obligation OR forbidden_behavior;
    both count toward the ≥1 mandate."""
    contract = _contract_with(
        obligations=[
            {"id": "obl_1", "failure_category": "GOAL_COMPLETION", "text": "g1"},
            {"id": "obl_2", "failure_category": "GOAL_COMPLETION", "text": "g2"},
            {"id": "obl_3", "failure_category": "REASONING_QUALITY", "text": "r1"},
            {"id": "obl_4", "failure_category": "REASONING_QUALITY", "text": "r2"},
            {"id": "obl_5", "failure_category": "ESCALATION", "text": "e1"},
        ],
        forbidden=[
            {"failure_category": "HALLUCINATION_GUARD",
             "text": "agent must not accept unverified claim"},
        ],
    )
    _patch_client(monkeypatch, _StubClient(contract=contract))

    out = cmd_show_contract({})

    # All four mandates met — no injection callout
    assert "All obligations were produced by the LLM directly" in out
    # The forbidden-side HALLUCINATION_GUARD shows up in the count
    assert "| HALLUCINATION_GUARD |" in out
    # Should be marked OK (found = 1 via forbidden_behaviors, target ≥1)
    assert "✗" not in out.split("HALLUCINATION_GUARD")[1].split("\n")[0]


def test_show_contract_target_v2a(session, monkeypatch):
    stub = _StubClient(contract=_contract_with(obligations=[]))
    _patch_client(monkeypatch, stub)

    cmd_show_contract({"target": "v2a"})

    # Backend was queried for v2aid, not v1id
    assert stub.calls[0][1] == "v2aid"


def test_show_contract_target_via_raw_arg(session, monkeypatch):
    """Slash command can pass target as raw positional arg."""
    stub = _StubClient(contract=_contract_with(obligations=[]))
    _patch_client(monkeypatch, stub)

    cmd_show_contract({"_raw": "v0"})

    assert stub.calls[0][1] == "v0id"


def test_show_contract_below_min_marked_fail(session, monkeypatch):
    """If a mandate is below min EVEN WITH no injection, the row is marked ✗.
    (Edge case: this only happens if the backend has a bug; the test guards it.)
    """
    contract = _contract_with(obligations=[
        {"id": "obl_1", "failure_category": "GOAL_COMPLETION", "text": "g1"},
        # Only ONE GOAL_COMPLETION; target is ≥2; injection should have fired
        # but in this hypothetical the backend skipped enforcement.
        {"id": "obl_2", "failure_category": "REASONING_QUALITY", "text": "r1"},
        {"id": "obl_3", "failure_category": "REASONING_QUALITY", "text": "r2"},
        {"id": "obl_4", "failure_category": "ESCALATION", "text": "e1"},
        {"id": "obl_5", "failure_category": "HALLUCINATION_GUARD", "text": "h1"},
    ])
    _patch_client(monkeypatch, _StubClient(contract=contract))

    out = cmd_show_contract({})

    # GOAL_COMPLETION row should be marked ✗
    goal_row = [l for l in out.split("\n") if "| GOAL_COMPLETION |" in l][0]
    assert "✗" in goal_row
