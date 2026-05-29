"""Unit tests for cmd_deploy_gate.

Mocks AssertenClient.run_deploy_gate to return a GateResult or raise
AssertenError. Verifies:
  - early-guard branches (no session, bad target)
  - PASSED verdict rendered with the ✓ glyph
  - BLOCKED verdict rendered with the 🛑 glyph + regression table
  - AssertenError (HTTP 400, no eval) surfaced as a friendly message,
    not a stack trace, and last_error persisted to session
  - default targets candidate=v2b, baseline=v1
"""
from __future__ import annotations

import pytest

from client.api import AssertenError
from client.cli import cmd_deploy_gate
from client.models import GateResult, SessionState
from client.session import load_session, save_session


@pytest.fixture
def session_full(tmp_path, monkeypatch):
    sp = tmp_path / "session.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(sp))
    save_session(SessionState(
        backend_url="http://test", api_key="k", agent_id="a1",
        v1_version_id="v1id", v2b_version_id="v2bid",
    ))
    return sp


class _StubClient:
    def __init__(self, *, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.calls: list[tuple] = []
        self.kwargs_calls: list[dict] = []

    def run_deploy_gate(self, agent_id, candidate_version_id,
                        baseline_version_id=None, **kwargs):
        self.calls.append((agent_id, candidate_version_id, baseline_version_id))
        self.kwargs_calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.result


def _patch_client(monkeypatch, stub) -> None:
    import client.cli
    monkeypatch.setattr(client.cli, "_client", lambda _state: stub)


def test_deploy_gate_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(tmp_path / "s.json"))
    out = cmd_deploy_gate({})
    assert "No agent in session" in out


def test_deploy_gate_unknown_target(session_full, monkeypatch):
    _patch_client(monkeypatch, _StubClient(result=None))
    out = cmd_deploy_gate({"candidate": "v99"})
    assert "unknown target" in out


def test_deploy_gate_passed(session_full, monkeypatch):
    result = GateResult(
        verdict="PASSED", candidate_version_id="v2bid", baseline_version_id="v1id",
        approved_count=3, regressions=[], improvements=[{"test_case_id": "tc_i"}],
        stable_pass=[{"test_case_id": "tc_a"}, {"test_case_id": "tc_b"}],
        stable_fail=[], coverage_gaps=[],
        reason="No regressions on the approved set.")
    stub = _StubClient(result=result)
    _patch_client(monkeypatch, stub)

    out = cmd_deploy_gate({"candidate": "v2b", "baseline": "v1"})

    assert "✓ PASSED" in out
    assert "3 approved scenarios" in out
    assert "1 improvement" in out and "2 stable_pass" in out
    # default + explicit both resolve correctly
    assert stub.calls[0] == ("a1", "v2bid", "v1id")


def test_deploy_gate_blocked_shows_regression_table(session_full, monkeypatch):
    result = GateResult(
        verdict="BLOCKED", candidate_version_id="v2bid", baseline_version_id="v1id",
        approved_count=2,
        regressions=[{
            "test_case_id": "tc_reg", "scenario_name": "Refund within policy",
            "baseline_status": "passed", "candidate_status": "failed",
            "failure_origin": "agent", "candidate_reason": "denied a valid refund"}],
        improvements=[], stable_pass=[{"test_case_id": "tc_ok"}],
        stable_fail=[], coverage_gaps=[],
        reason="1 approved scenario regressed.")
    stub = _StubClient(result=result)
    _patch_client(monkeypatch, stub)

    out = cmd_deploy_gate({})  # defaults candidate=v2b, baseline=v1

    assert "🛑 BLOCKED" in out
    assert "Regressions" in out
    assert "Refund within policy" in out
    assert "passed → failed" in out
    assert "agent" in out
    assert "denied a valid refund" in out
    assert stub.calls[0] == ("a1", "v2bid", "v1id")


def test_deploy_gate_no_eval_400_surfaced_friendly(session_full, monkeypatch):
    err = AssertenError(
        status=400,
        body="Candidate version v2bid has no eval runs; run /asserten-eval on it first.",
        url="http://test/agents/a1/versions/v2bid/deploy-gate")
    stub = _StubClient(raises=err)
    _patch_client(monkeypatch, stub)

    out = cmd_deploy_gate({})

    assert "Gate could not run" in out
    assert "no eval runs" in out
    # no raw traceback leaked
    assert "Traceback" not in out
    # last_error persisted for forensics
    after = load_session()
    assert after.last_error and "no eval runs" in after.last_error


def test_deploy_gate_forwards_auto_eval_flag(session_full, monkeypatch):
    result = GateResult(verdict="PASSED", candidate_version_id="v2bid",
                        baseline_version_id="v1id", approved_count=1, reason="ok")
    stub = _StubClient(result=result)
    _patch_client(monkeypatch, stub)
    cmd_deploy_gate({"candidate": "v2b", "baseline": "v1", "auto_eval": False})
    assert stub.kwargs_calls[-1].get("auto_eval") is False


def test_deploy_gate_forwards_strict_flag(session_full, monkeypatch):
    result = GateResult(verdict="PASSED", candidate_version_id="v2bid",
                        baseline_version_id="v1id", approved_count=1, reason="ok")
    stub = _StubClient(result=result)
    _patch_client(monkeypatch, stub)
    cmd_deploy_gate({"candidate": "v2b", "baseline": "v1", "strict": False})
    assert stub.kwargs_calls[-1].get("strict") is False


def test_deploy_gate_renders_inconclusive(session_full, monkeypatch):
    result = GateResult(verdict="INCONCLUSIVE", candidate_version_id="v2bid",
                        baseline_version_id="v1id", approved_count=2,
                        candidate_eval_invalid=True, candidate_judge_error_rate=0.4,
                        reason="Cannot certify: candidate eval melted down.")
    stub = _StubClient(result=result)
    _patch_client(monkeypatch, stub)
    out = cmd_deploy_gate({"candidate": "v2b", "baseline": "v1"})
    assert "INCONCLUSIVE" in out


def test_deploy_gate_auto_eval_defaults_true(session_full, monkeypatch):
    result = GateResult(verdict="PASSED", candidate_version_id="v2bid",
                        baseline_version_id="v1id", approved_count=1, reason="ok")
    stub = _StubClient(result=result)
    _patch_client(monkeypatch, stub)
    cmd_deploy_gate({"candidate": "v2b", "baseline": "v1"})
    assert stub.kwargs_calls[-1].get("auto_eval") is True


def test_deploy_gate_passed_no_approved(session_full, monkeypatch):
    result = GateResult(
        verdict="PASSED_NO_APPROVED", candidate_version_id="v2bid",
        baseline_version_id="v1id", approved_count=0,
        reason="No approved scenarios on the candidate version — the gate is a no-op.")
    _patch_client(monkeypatch, _StubClient(result=result))
    out = cmd_deploy_gate({})
    assert "no approved scenarios" in out.lower()
    assert "0 approved scenario" in out  # singular phrasing for zero
