"""Unit tests for cmd_approve / cmd_unapprove.

Mocks AssertenClient so no live backend. Verifies:
  - early-guard branches (no session, no ids, bad target)
  - success path: backend called with right (agent, version, ids); response surfaced
  - idempotent already_approved / already_unapproved surfaced as no-op note
  - not_found ids surfaced
  - raw comma-separated input parsed into a list
  - forensics: `last_test_case_op` persisted with op=approve/unapprove
"""
from __future__ import annotations

import pytest

from client.cli import cmd_approve, cmd_unapprove
from client.models import SessionState
from client.session import load_session, save_session


@pytest.fixture
def session_with_v1(tmp_path, monkeypatch):
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
    def __init__(self, *, approve_returns=None, unapprove_returns=None):
        self.approve_returns = approve_returns or {
            "approved": [], "not_found": [], "already_approved": []}
        self.unapprove_returns = unapprove_returns or {
            "unapproved": [], "not_found": [], "already_unapproved": []}
        self.approve_calls: list[tuple] = []
        self.unapprove_calls: list[tuple] = []

    def approve_test_cases(self, agent_id, version_id, ids):
        self.approve_calls.append((agent_id, version_id, ids))
        return self.approve_returns

    def unapprove_test_cases(self, agent_id, version_id, ids):
        self.unapprove_calls.append((agent_id, version_id, ids))
        return self.unapprove_returns


def _patch_client(monkeypatch, stub: _StubClient) -> None:
    import client.cli
    monkeypatch.setattr(client.cli, "_client", lambda _state: stub)


# ── early-guard branches ────────────────────────────────────────────────────


def test_approve_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(tmp_path / "s.json"))
    out = cmd_approve({"test_case_ids": ["tc_1"]})
    assert "No agent in session" in out


def test_approve_no_ids(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_approve({})
    assert "comma-separated list" in out


def test_approve_unknown_target(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_approve({"test_case_ids": ["tc_1"], "target": "v99"})
    assert "unknown target" in out


def test_approve_target_not_in_session(tmp_path, monkeypatch):
    sp = tmp_path / "session.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(sp))
    save_session(SessionState(backend_url="http://x", agent_id="a1"))  # no v2b
    _patch_client(monkeypatch, _StubClient())
    out = cmd_approve({"test_case_ids": ["tc_1"], "target": "v2b"})
    assert "no v2b in session" in out


# ── success path + forensics ────────────────────────────────────────────────


def test_approve_success_calls_backend_and_records_op(session_with_v1, monkeypatch):
    # Real backend contract: `approved` is the full guaranteed set after the
    # call; `already_approved` ⊆ approved. Two fresh approvals → both in
    # `approved`, none in `already_approved`.
    stub = _StubClient(approve_returns={
        "approved": ["tc_1", "tc_2"], "not_found": [], "already_approved": []})
    _patch_client(monkeypatch, stub)

    out = cmd_approve({"test_case_ids": ["tc_1", "tc_2"]})

    assert "**Approved 2 new case(s)**" in out and "on v1" in out
    assert "no-regression promise" in out  # follow-up nudge present
    # Backend got the right args, routed to v1
    assert len(stub.approve_calls) == 1
    agent_id, version_id, ids = stub.approve_calls[0]
    assert agent_id == "a1" and version_id == "v1id"
    assert ids == ["tc_1", "tc_2"]
    # Forensics: op recorded with the full result blob
    after = load_session()
    assert after.last_test_case_op["op"] == "approve"
    assert after.last_test_case_op["target"] == "v1"
    assert after.last_test_case_op["approved"] == ["tc_1", "tc_2"]


def test_approve_already_approved_is_noop_note(session_with_v1, monkeypatch):
    # Real backend puts an already-approved id in BOTH lists (approved is the
    # full guaranteed set; already_approved is the no-op subset). Newly-flipped
    # = len(approved) - len(already_approved) = 0.
    stub = _StubClient(approve_returns={
        "approved": ["tc_1"], "not_found": [], "already_approved": ["tc_1"]})
    _patch_client(monkeypatch, stub)
    out = cmd_approve({"test_case_ids": ["tc_1"]})
    assert "Approved 0 new case(s)" in out
    assert "1 now in the guaranteed set" in out
    assert "1 were already approved" in out


def test_approve_not_found_surfaced(session_with_v1, monkeypatch):
    stub = _StubClient(approve_returns={
        "approved": ["tc_1"], "not_found": ["tc_nope"], "already_approved": []})
    _patch_client(monkeypatch, stub)
    out = cmd_approve({"test_case_ids": ["tc_1", "tc_nope"]})
    assert "Approved 1 new case(s)" in out
    assert "Not found at this version: tc_nope" in out


def test_approve_raw_csv_parsed(session_with_v1, monkeypatch):
    stub = _StubClient(approve_returns={
        "approved": ["tc_1", "tc_2"], "not_found": [], "already_approved": []})
    _patch_client(monkeypatch, stub)
    cmd_approve({"_raw": "tc_1, tc_2"})
    assert stub.approve_calls[0][2] == ["tc_1", "tc_2"]


def test_approve_target_v2a_routes(session_with_v1, monkeypatch):
    stub = _StubClient(approve_returns={
        "approved": ["tc_1"], "not_found": [], "already_approved": []})
    _patch_client(monkeypatch, stub)
    cmd_approve({"test_case_ids": ["tc_1"], "target": "v2a"})
    assert stub.approve_calls[0][1] == "v2aid"  # routed to v2a not v1
    after = load_session()
    assert after.last_test_case_op["target"] == "v2a"


# ── unapprove ────────────────────────────────────────────────────────────────


def test_unapprove_no_ids(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_unapprove({})
    assert "comma-separated list" in out


def test_unapprove_success_records_op(session_with_v1, monkeypatch):
    stub = _StubClient(unapprove_returns={
        "unapproved": ["tc_1"], "not_found": [], "already_unapproved": []})
    _patch_client(monkeypatch, stub)
    out = cmd_unapprove({"test_case_ids": ["tc_1"]})
    assert "**Unapproved 1 case(s)**" in out and "on v1" in out
    after = load_session()
    assert after.last_test_case_op["op"] == "unapprove"
    assert after.last_test_case_op["unapproved"] == ["tc_1"]


def test_unapprove_already_unapproved_is_noop_note(session_with_v1, monkeypatch):
    # Mirror of approve: already-unapproved id appears in BOTH lists.
    stub = _StubClient(unapprove_returns={
        "unapproved": ["tc_1"], "not_found": [], "already_unapproved": ["tc_1"]})
    _patch_client(monkeypatch, stub)
    out = cmd_unapprove({"test_case_ids": ["tc_1"]})
    assert "Unapproved 0 case(s)" in out
    assert "1 were already unapproved" in out
