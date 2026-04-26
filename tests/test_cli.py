"""Smoke tests for the CLI dispatcher — routing, error handling, JSON parsing."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


CLI = [sys.executable, "-m", "client.cli"]
ROOT = Path(__file__).parent.parent


def _run(*args, env_extra=None, stdin: str | None = None) -> tuple[int, str]:
    """Invoke the CLI in a subprocess. Returns (exit_code, stdout)."""
    import os
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    cwd = str(ROOT)
    proc = subprocess.run(
        CLI + list(args), cwd=cwd, env=env, input=stdin, capture_output=True,
        text=True, timeout=30,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_status_with_no_session(tmp_path):
    code, out = _run("status",
                     env_extra={"ASSERTEN_SESSION_PATH": str(tmp_path / "s.json")})
    assert code == 0
    assert "No active session" in out


def test_reset_idempotent(tmp_path):
    code, out = _run("reset",
                     env_extra={"ASSERTEN_SESSION_PATH": str(tmp_path / "s.json")})
    assert code == 0
    assert "No session to clear" in out or "cleared" in out


def test_compare_with_empty_session_renders_table(tmp_path):
    code, out = _run("compare",
                     env_extra={"ASSERTEN_SESSION_PATH": str(tmp_path / "s.json")})
    assert code == 0
    assert "v0 (raw)" in out
    assert "v2a (LIGHT optimize)" in out


def test_unknown_subcommand_exits_nonzero(tmp_path):
    code, out = _run("garbage",
                     env_extra={"ASSERTEN_SESSION_PATH": str(tmp_path / "s.json")})
    assert code != 0
    assert "Available subcommands" in out


def test_eval_unknown_target_returns_message(tmp_path):
    """Pre-condition: no v0 yet, so eval will reject."""
    code, out = _run("eval", '{"target":"v99"}',
                     env_extra={"ASSERTEN_SESSION_PATH": str(tmp_path / "s.json")})
    assert code == 0
    assert "Unknown target" in out


def test_select_without_audit_returns_message(tmp_path):
    code, out = _run("select", '{"answer":"all"}',
                     env_extra={"ASSERTEN_SESSION_PATH": str(tmp_path / "s.json")})
    assert code == 0
    assert "No suggested patches" in out


def test_optimize_light_without_candidates_returns_message(tmp_path):
    code, out = _run("optimize-light",
                     env_extra={"ASSERTEN_SESSION_PATH": str(tmp_path / "s.json")})
    assert code == 0
    assert "candidate v1" in out.lower()


def test_subcommand_accepts_stdin_json(tmp_path):
    """Dispatcher should read JSON from stdin if argv[2] is missing."""
    code, out = _run("eval",
                     stdin='{"target":"v0"}',
                     env_extra={"ASSERTEN_SESSION_PATH": str(tmp_path / "s.json")})
    assert code == 0
    # No agent yet → "No `v0` version in session yet."
    assert "v0" in out


def test_session_writes_file_after_status(tmp_path):
    """Status doesn't mutate; file should NOT exist after read-only call."""
    sp = tmp_path / "s.json"
    _run("status", env_extra={"ASSERTEN_SESSION_PATH": str(sp)})
    assert not sp.exists()  # status only loads, never saves


def test_reset_removes_existing_session_file(tmp_path):
    sp = tmp_path / "s.json"
    sp.write_text('{"backend_url":"http://x","agent_id":"a"}')
    code, out = _run("reset", env_extra={"ASSERTEN_SESSION_PATH": str(sp)})
    assert code == 0
    assert not sp.exists()
    assert "cleared" in out.lower()
