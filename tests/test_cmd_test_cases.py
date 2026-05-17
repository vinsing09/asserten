"""Unit tests for cmd_add_tests, cmd_skip_tests, cmd_unskip_tests.

Mocks AssertenClient so no live backend. Verifies:
  - early-guard branches (no session, no input, bad target)
  - success path: backend called with the right shape, response surfaced
  - forensics: `last_test_case_op` persisted in session for later inspection
  - per-case error isolation: bad cases reported, good ones still inserted
  - file-input path: reads JSON from disk; handles missing file + bad JSON
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from client.cli import cmd_add_tests, cmd_skip_tests, cmd_unskip_tests
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
    ))
    return sp


class _StubClient:
    def __init__(self, *, add_returns=None, skip_returns=None,
                 unskip_returns=None, add_raises=None):
        self.add_returns = add_returns or {"inserted": [], "errors": []}
        self.skip_returns = skip_returns or {"skipped": [], "not_found": []}
        self.unskip_returns = unskip_returns or {"unskipped": [], "not_found": []}
        self.add_raises = add_raises
        self.add_calls: list[tuple] = []
        self.skip_calls: list[tuple] = []
        self.unskip_calls: list[tuple] = []

    def add_user_test_cases(self, agent_id, version_id, test_cases):
        if self.add_raises is not None:
            raise self.add_raises
        self.add_calls.append((agent_id, version_id, test_cases))
        return self.add_returns

    def skip_test_cases(self, agent_id, version_id, ids):
        self.skip_calls.append((agent_id, version_id, ids))
        return self.skip_returns

    def unskip_test_cases(self, agent_id, version_id, ids):
        self.unskip_calls.append((agent_id, version_id, ids))
        return self.unskip_returns


def _patch_client(monkeypatch, stub: _StubClient) -> None:
    import client.cli
    monkeypatch.setattr(client.cli, "_client", lambda _state: stub)


# ── early-guard branches ────────────────────────────────────────────────────


def test_add_tests_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(tmp_path / "s.json"))
    out = cmd_add_tests({"test_cases": [{"scenario": "x"}]})
    assert "No agent in session" in out


def test_add_tests_no_input(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_add_tests({})
    assert "No test cases provided" in out


def test_add_tests_raw_arg_gives_help(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_add_tests({"_raw": "hello"})
    assert "Pass either" in out


def test_add_tests_empty_list_rejected(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_add_tests({"test_cases": []})
    assert "non-empty list" in out


def test_add_tests_unknown_target(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_add_tests({"test_cases": [{"scenario": "x"}], "target": "v99"})
    assert "unknown target" in out


def test_add_tests_target_not_in_session(tmp_path, monkeypatch):
    sp = tmp_path / "session.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(sp))
    save_session(SessionState(backend_url="http://x", agent_id="a1"))  # no v1
    _patch_client(monkeypatch, _StubClient())
    out = cmd_add_tests({"test_cases": [{"scenario": "x"}], "target": "v1"})
    assert "no v1 in session" in out


# ── success path + forensics ────────────────────────────────────────────────


def test_add_tests_success_calls_backend_and_records_op(session_with_v1, monkeypatch):
    stub = _StubClient(add_returns={
        "inserted": [{"id": "tc_abc12345", "scenario": "refund"}],
        "errors": [],
    })
    _patch_client(monkeypatch, stub)

    out = cmd_add_tests({"test_cases": [{"scenario": "refund", "input_text": "..."}]})

    assert "Added 1 test case(s) to v1" in out
    assert "Full per-case result saved" in out
    # Backend got the right args
    assert len(stub.add_calls) == 1
    agent_id, version_id, cases = stub.add_calls[0]
    assert agent_id == "a1" and version_id == "v1id"
    assert cases[0]["scenario"] == "refund"
    # Session captured the op for forensics
    after = load_session()
    assert after.last_test_case_op["op"] == "add"
    assert after.last_test_case_op["target"] == "v1"
    assert after.last_test_case_op["inserted"][0]["id"] == "tc_abc12345"


def test_add_tests_partial_failure_surfaces_per_case_errors(session_with_v1, monkeypatch):
    stub = _StubClient(add_returns={
        "inserted": [{"id": "tc_1", "scenario": "good"}],
        "errors": [{"index": 1, "scenario": "bad",
                    "error": "unknown tool names: ['fake_tool']"}],
    })
    _patch_client(monkeypatch, stub)

    out = cmd_add_tests({"test_cases": [
        {"scenario": "good", "input_text": "x"},
        {"scenario": "bad", "input_text": "y", "tool_stubs": {"fake_tool": {}}},
    ]})

    assert "Added 1 test case(s)" in out
    assert "1 case(s) rejected" in out
    assert "fake_tool" in out
    assert "case #1" in out  # per-case index surfaced
    # Forensics record has both inserted AND errors
    after = load_session()
    assert len(after.last_test_case_op["inserted"]) == 1
    assert len(after.last_test_case_op["errors"]) == 1


def test_add_tests_unknown_obligation_id_is_warning_not_error(session_with_v1, monkeypatch):
    stub = _StubClient(add_returns={
        "inserted": [{"id": "tc_1", "scenario": "x",
                      "warnings": ["unknown obligation_ids: ['obl_missing']"]}],
        "errors": [],
    })
    _patch_client(monkeypatch, stub)

    out = cmd_add_tests({"test_cases": [{"scenario": "x", "obligation_ids": ["obl_missing"]}]})

    assert "Added 1 test case(s)" in out
    assert "warnings (non-fatal)" in out
    assert "obl_missing" in out


def test_add_tests_target_v2a_resolves(tmp_path, monkeypatch):
    sp = tmp_path / "session.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(sp))
    save_session(SessionState(backend_url="http://x", agent_id="a1",
                              v1_version_id="v1id", v2a_version_id="v2aid"))
    stub = _StubClient(add_returns={"inserted": [{"id": "t", "scenario": "x"}],
                                    "errors": []})
    _patch_client(monkeypatch, stub)

    cmd_add_tests({"test_cases": [{"scenario": "x"}], "target": "v2a"})

    assert stub.add_calls[0][1] == "v2aid"  # routed to v2a not v1
    after = load_session()
    assert after.last_test_case_op["target"] == "v2a"


# ── file-input path ─────────────────────────────────────────────────────────


def test_add_tests_from_file_object_shape(session_with_v1, tmp_path, monkeypatch):
    p = tmp_path / "cases.json"
    p.write_text(json.dumps({"test_cases": [{"scenario": "fromfile",
                                              "input_text": "x"}]}))
    stub = _StubClient(add_returns={"inserted": [{"id": "t", "scenario": "fromfile"}],
                                     "errors": []})
    _patch_client(monkeypatch, stub)

    cmd_add_tests({"file": str(p)})

    assert stub.add_calls[0][2][0]["scenario"] == "fromfile"


def test_add_tests_from_file_bare_list(session_with_v1, tmp_path, monkeypatch):
    p = tmp_path / "cases.json"
    p.write_text(json.dumps([{"scenario": "bare", "input_text": "x"}]))
    stub = _StubClient(add_returns={"inserted": [{"id": "t", "scenario": "bare"}],
                                     "errors": []})
    _patch_client(monkeypatch, stub)

    cmd_add_tests({"file": str(p)})

    assert stub.add_calls[0][2][0]["scenario"] == "bare"


def test_add_tests_file_not_found(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_add_tests({"file": "/nonexistent/path.json"})
    assert "File not found" in out


def test_add_tests_file_bad_json(session_with_v1, tmp_path, monkeypatch):
    p = tmp_path / "broken.json"
    p.write_text("{not valid json")
    _patch_client(monkeypatch, _StubClient())
    out = cmd_add_tests({"file": str(p)})
    assert "Invalid JSON" in out


# ── skip / unskip ───────────────────────────────────────────────────────────


def test_skip_tests_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(tmp_path / "s.json"))
    out = cmd_skip_tests({"test_case_ids": ["tc_1"]})
    assert "No agent in session" in out


def test_skip_tests_no_ids(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient())
    out = cmd_skip_tests({})
    assert "comma-separated list" in out


def test_skip_tests_raw_csv_parsed(session_with_v1, monkeypatch):
    stub = _StubClient(skip_returns={"skipped": ["tc_1", "tc_2"], "not_found": []})
    _patch_client(monkeypatch, stub)
    cmd_skip_tests({"_raw": "tc_1, tc_2"})
    assert stub.skip_calls[0][2] == ["tc_1", "tc_2"]


def test_skip_tests_success_records_op(session_with_v1, monkeypatch):
    stub = _StubClient(skip_returns={"skipped": ["tc_1"], "not_found": ["tc_nope"]})
    _patch_client(monkeypatch, stub)
    out = cmd_skip_tests({"test_case_ids": ["tc_1", "tc_nope"]})
    assert "Skipped 1 case(s)" in out
    assert "1 id(s) not found" in out
    after = load_session()
    assert after.last_test_case_op["op"] == "skip"
    assert after.last_test_case_op["skipped"] == ["tc_1"]
    assert after.last_test_case_op["not_found"] == ["tc_nope"]


def test_unskip_tests_success_records_op(session_with_v1, monkeypatch):
    stub = _StubClient(unskip_returns={"unskipped": ["tc_1"], "not_found": []})
    _patch_client(monkeypatch, stub)
    out = cmd_unskip_tests({"test_case_ids": ["tc_1"]})
    assert "Un-skipped 1 case(s)" in out
    after = load_session()
    assert after.last_test_case_op["op"] == "unskip"
    assert after.last_test_case_op["unskipped"] == ["tc_1"]


def test_status_surfaces_last_test_case_op(session_with_v1, monkeypatch):
    """End-to-end forensics: after add-tests, /asserten-status shows the op."""
    stub = _StubClient(add_returns={"inserted": [{"id": "t", "scenario": "x"}],
                                     "errors": [{"index": 0, "scenario": "bad",
                                                 "error": "boom"}]})
    _patch_client(monkeypatch, stub)
    cmd_add_tests({"test_cases": [{"scenario": "x"}]})

    from client.cli import cmd_status
    out = cmd_status({})
    assert "last test-case op: `add`" in out
    assert "inserted=1" in out
    assert "errors=1" in out
