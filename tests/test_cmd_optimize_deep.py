"""Unit tests for cmd_optimize_deep — covers the three real branches:
  1. job status != completed → friendly retry message + counter incremented
  2. job completed + 0 suggestions → "couldn't produce a valid patch" + counter
  3. job completed + N suggestions → apply succeeds + v2b_version_id recorded

Mocks the AssertenClient so no live LLM / backend traffic.
"""
import json
from pathlib import Path

import pytest

from client.cli import cmd_optimize_deep
from client.models import SessionState
from client.session import save_session


@pytest.fixture
def session_with_v1(tmp_path, monkeypatch):
    """Pre-seed a session with v1 set so cmd_optimize_deep proceeds past the
    early guards. Returns the session path so the test can read it back."""
    sp = tmp_path / "session.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(sp))
    save_session(SessionState(
        backend_url="http://test",
        api_key="k",
        agent_id="a1",
        v1_version_id="v1id",
    ))
    return sp


class _StubClient:
    def __init__(self, *, job_status: str, suggestions: list,
                 apply_returns: str = "v2b_id", apply_raises: Exception | None = None):
        self.job_status = job_status
        self.suggestions = suggestions
        self.apply_returns = apply_returns
        self.apply_raises = apply_raises

    def optimize_deep(self, *_args, **_kw):
        return {"job_id": "job-12345"}

    def wait_improvement_job(self, *_args, **_kw):
        return {"job_id": "job-12345", "status": self.job_status,
                "suggestions": self.suggestions}

    def apply_improvements(self, *_args, **_kw):
        if self.apply_raises is not None:
            raise self.apply_raises
        return self.apply_returns


def _patch_client(monkeypatch, stub: _StubClient) -> None:
    import client.cli
    monkeypatch.setattr(client.cli, "_client", lambda _state: stub)


def test_no_v1_returns_early(session_with_v1, monkeypatch):
    """Edge: blank v1 in session → guard kicks in before any client call."""
    save_session(SessionState(backend_url="http://test", api_key="k"))  # no v1
    out = cmd_optimize_deep({"eval_run_id": "e1"})
    assert "No v1" in out


def test_no_eval_run_id_returns_early(session_with_v1):
    out = cmd_optimize_deep({})
    assert "Pass `eval_run_id`" in out


def test_failed_job_increments_counter_and_surfaces_status(session_with_v1, monkeypatch):
    stub = _StubClient(job_status="failed", suggestions=[])
    _patch_client(monkeypatch, stub)
    out = cmd_optimize_deep({"eval_run_id": "e1"})
    assert "attempt #1" in out
    assert "`failed`" in out
    state = json.loads(session_with_v1.read_text())
    assert state["v2b_attempts"] == 1
    assert state["v2b_last_status"] == "failed"
    # No v2b version on a failed run.
    assert state["v2b_version_id"] == ""


def test_zero_suggestions_returns_friendly_message(session_with_v1, monkeypatch):
    """The case overnight DEEP run on bea9a565 hit: completed + empty suggestions."""
    stub = _StubClient(job_status="completed", suggestions=[])
    _patch_client(monkeypatch, stub)
    out = cmd_optimize_deep({"eval_run_id": "e1"})
    assert "attempt #1" in out
    assert "couldn't produce a valid patch" in out
    assert "v2b unavailable" in out
    # No mention of "cross-refine" — user wants the user-facing wording to stay
    # at "deep optimisation" (the public name) only.
    assert "cross-refine" not in out.lower()
    state = json.loads(session_with_v1.read_text())
    assert state["v2b_attempts"] == 1
    assert state["v2b_last_status"] == "no_valid_patch"
    assert state["v2b_version_id"] == ""


def test_attempts_counter_increments_across_runs(session_with_v1, monkeypatch):
    stub = _StubClient(job_status="completed", suggestions=[])
    _patch_client(monkeypatch, stub)
    cmd_optimize_deep({"eval_run_id": "e1"})
    cmd_optimize_deep({"eval_run_id": "e1"})
    out = cmd_optimize_deep({"eval_run_id": "e1"})
    assert "attempt #3" in out
    state = json.loads(session_with_v1.read_text())
    assert state["v2b_attempts"] == 3


def test_successful_apply_records_v2b_version_id(session_with_v1, monkeypatch):
    suggestions = [
        {"id": "fix_1", "target_slot": "main_prompt", "tool_filter": "all",
         "on_error_only": False, "prompt_patch": "be polite"},
        {"id": "fix_2", "target_slot": "main_prompt", "tool_filter": "all",
         "on_error_only": False, "prompt_patch": "confirm before refund"},
    ]
    stub = _StubClient(job_status="completed", suggestions=suggestions,
                       apply_returns="v2b-abc123")
    _patch_client(monkeypatch, stub)
    out = cmd_optimize_deep({"eval_run_id": "e1"})
    assert "attempt #1" in out
    assert "2 patch(es) applied" in out
    assert "v2b-abc1" in out  # short prefix shown
    state = json.loads(session_with_v1.read_text())
    assert state["v2b_version_id"] == "v2b-abc123"
    assert state["v2b_attempts"] == 1
    assert state["v2b_last_status"] == "ok"


def test_apply_failure_records_attempt_but_no_v2b(session_with_v1, monkeypatch):
    suggestions = [{"id": "fix_1", "prompt_patch": "x"}]
    stub = _StubClient(
        job_status="completed", suggestions=suggestions,
        apply_raises=RuntimeError("422 unprocessable"),
    )
    _patch_client(monkeypatch, stub)
    out = cmd_optimize_deep({"eval_run_id": "e1"})
    assert "attempt #1" in out
    assert "apply failed" in out
    assert "422" in out
    state = json.loads(session_with_v1.read_text())
    assert state["v2b_version_id"] == ""
    assert state["v2b_last_status"] == "apply_failed"
