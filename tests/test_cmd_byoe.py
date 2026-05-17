"""Unit tests for cmd_byoe — the BYOE simple-shape entry command."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from client.api import AssertenError
from client.cli import cmd_byoe, cmd_status
from client.models import SessionState
from client.session import load_session, save_session


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
    def __init__(self, *, returns=None, raises=None):
        self.returns = returns or {"inserted": [], "errors": []}
        self.raises = raises
        self.calls: list[tuple] = []

    def add_byoe_test_cases(self, agent_id, version_id, cases):
        if self.raises is not None:
            raise self.raises
        self.calls.append((agent_id, version_id, cases))
        return self.returns


def _patch_client(monkeypatch, stub):
    import client.cli
    monkeypatch.setattr(client.cli, "_client", lambda _state: stub)


# ── early guards ────────────────────────────────────────────────────────────


def test_byoe_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(tmp_path / "s.json"))
    out = cmd_byoe({"test_cases": [{"input": "x"}]})
    assert "No agent in session" in out


def test_byoe_no_input(session, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_byoe({})
    assert "No test cases provided" in out


def test_byoe_raw_arg_gives_help(session, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_byoe({"_raw": "just text"})
    assert "Pass" in out
    assert "agent_should_say" in out


def test_byoe_empty_list_rejected(session, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_byoe({"test_cases": []})
    assert "non-empty list" in out


def test_byoe_unknown_target(session, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_byoe({"test_cases": [{"input": "x"}], "target": "v99"})
    assert "unknown target" in out


# ── success path + forensics ────────────────────────────────────────────────


def test_byoe_success_calls_backend_and_records_op(session, monkeypatch):
    stub = _StubClient(returns={
        "inserted": [{"id": "tc_abc12345", "scenario": "refund flow"}],
        "errors": [],
    })
    _patch_client(monkeypatch, stub)

    cases = [{"input": "I want a refund", "agent_should_say": ["order ID"]}]
    out = cmd_byoe({"test_cases": cases})

    assert "Added 1 BYOE test case(s) to v1" in out
    assert "refund flow" in out
    assert stub.calls[0][1] == "v1id"
    assert stub.calls[0][2] == cases
    # Session captures op for forensics
    after = load_session()
    assert after.last_test_case_op["op"] == "byoe"
    assert after.last_test_case_op["target"] == "v1"
    assert after.last_test_case_op["inserted"][0]["id"] == "tc_abc12345"


def test_byoe_partial_failure_surfaces_per_case_errors(session, monkeypatch):
    stub = _StubClient(returns={
        "inserted": [{"id": "tc_1", "scenario": "good"}],
        "errors": [{"index": 1, "input": "bad case",
                    "error": "agent_should_call references unknown tools ['fake_tool']"}],
    })
    _patch_client(monkeypatch, stub)

    out = cmd_byoe({"test_cases": [
        {"input": "good"},
        {"input": "bad case", "agent_should_call": ["fake_tool"]},
    ]})

    assert "Added 1 BYOE test case(s)" in out
    assert "1 case(s) rejected" in out
    assert "fake_tool" in out
    assert "case #1" in out


def test_byoe_fallback_called_out_explicitly(session, monkeypatch):
    """When the backend's LLM enrichment fails, the inserted entry carries
    fallback_reason — the CLI must surface that prominently."""
    stub = _StubClient(returns={
        "inserted": [
            {"id": "tc_ok", "scenario": "good case"},
            {"id": "tc_fb", "scenario": "I want a refund",
             "fallback_reason": "RuntimeError: LLM API down"},
        ],
        "errors": [],
    })
    _patch_client(monkeypatch, stub)

    out = cmd_byoe({"test_cases": [
        {"input": "good"},
        {"input": "I want a refund"},
    ]})

    assert "Added 2 BYOE test case(s)" in out
    assert "1 case(s) used deterministic fallback" in out
    assert "LLM API down" in out


def test_byoe_target_v2a(session, monkeypatch):
    stub = _StubClient(returns={"inserted": [{"id": "t", "scenario": "x"}],
                                "errors": []})
    _patch_client(monkeypatch, stub)

    cmd_byoe({"test_cases": [{"input": "x"}], "target": "v2a"})

    assert stub.calls[0][1] == "v2aid"
    after = load_session()
    assert after.last_test_case_op["target"] == "v2a"


# ── file input ──────────────────────────────────────────────────────────────


def test_byoe_from_file_object(session, tmp_path, monkeypatch):
    p = tmp_path / "byoe.json"
    p.write_text(json.dumps({"test_cases": [{
        "input": "from file", "agent_should_say": ["ok"],
    }]}))
    stub = _StubClient(returns={"inserted": [{"id": "t", "scenario": "from file"}],
                                "errors": []})
    _patch_client(monkeypatch, stub)

    cmd_byoe({"file": str(p)})

    assert stub.calls[0][2][0]["input"] == "from file"


def test_byoe_from_file_bare_list(session, tmp_path, monkeypatch):
    p = tmp_path / "byoe.json"
    p.write_text(json.dumps([{"input": "bare list"}]))
    stub = _StubClient(returns={"inserted": [{"id": "t", "scenario": "bare list"}],
                                "errors": []})
    _patch_client(monkeypatch, stub)

    cmd_byoe({"file": str(p)})

    assert stub.calls[0][2][0]["input"] == "bare list"


def test_byoe_file_not_found(session, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_byoe({"file": "/nonexistent/path.json"})
    assert "File not found" in out


def test_byoe_file_bad_json(session, tmp_path, monkeypatch):
    p = tmp_path / "broken.json"
    p.write_text("{not valid json")
    _patch_client(monkeypatch, _StubClient())
    out = cmd_byoe({"file": str(p)})
    assert "Invalid JSON" in out


# ── status surfacing ────────────────────────────────────────────────────────


def test_status_surfaces_byoe_op(session, monkeypatch):
    """After /asserten-byoe, /asserten-status shows last test-case op = byoe."""
    stub = _StubClient(returns={"inserted": [{"id": "t", "scenario": "x"}],
                                "errors": []})
    _patch_client(monkeypatch, stub)
    cmd_byoe({"test_cases": [{"input": "x"}]})

    out = cmd_status({})
    assert "last test-case op: `byoe`" in out
    assert "inserted=1" in out
