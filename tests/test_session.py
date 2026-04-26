"""Unit tests for client/session.py — load/save/update/reset roundtrips."""
import json
from pathlib import Path

import pytest

from client.session import (
    load_session, save_session, reset_session, update_session, session_path,
)
from client.models import SessionState


@pytest.fixture
def tmp_session(tmp_path, monkeypatch) -> Path:
    """Point asserten session at a tmp file."""
    p = tmp_path / "session.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(p))
    return p


def test_load_session_fresh_uses_default_backend(tmp_session, monkeypatch):
    monkeypatch.delenv("ASSERTEN_BACKEND_URL", raising=False)
    monkeypatch.delenv("ASSERTEN_API_KEY", raising=False)
    s = load_session()
    assert s.backend_url == "http://localhost:8000"
    assert s.api_key == ""


def test_load_session_fresh_respects_env(tmp_session, monkeypatch):
    monkeypatch.setenv("ASSERTEN_BACKEND_URL", "https://demo.asserten.dev")
    monkeypatch.setenv("ASSERTEN_API_KEY", "secret")
    s = load_session()
    assert s.backend_url == "https://demo.asserten.dev"
    assert s.api_key == "secret"


def test_save_then_load_roundtrip(tmp_session):
    s1 = SessionState(backend_url="http://x", api_key="k", agent_id="a")
    save_session(s1)
    s2 = load_session()
    assert s2.agent_id == "a"
    assert s2.api_key == "k"


def test_save_uses_atomic_replace(tmp_session):
    """Confirm tmp suffix is gone after save."""
    save_session(SessionState(backend_url="x"))
    assert not tmp_session.with_suffix(".json.tmp").exists()
    assert tmp_session.exists()


def test_update_session_merges_fields(tmp_session):
    save_session(SessionState(backend_url="x", agent_id="a"))
    s = update_session(v1_version_id="v1", v1_eval_pass_rate=95.0)
    assert s.agent_id == "a"  # preserved
    assert s.v1_version_id == "v1"
    assert s.v1_eval_pass_rate == 95.0


def test_update_session_ignores_unknown_field(tmp_session):
    save_session(SessionState(backend_url="x"))
    s = update_session(garbage=123)
    assert not hasattr(s, "garbage")


def test_reset_session_returns_true_when_present(tmp_session):
    save_session(SessionState(backend_url="x"))
    assert reset_session() is True
    assert not tmp_session.exists()


def test_reset_session_returns_false_when_absent(tmp_session):
    assert reset_session() is False


def test_load_session_recovers_from_corrupt_json(tmp_session):
    tmp_session.write_text("not json")
    s = load_session()
    assert s.backend_url  # falls back to default, doesn't crash


def test_load_session_override_args_take_precedence(tmp_session):
    save_session(SessionState(backend_url="from-disk", api_key="from-disk"))
    s = load_session(backend_url="override", api_key="key2")
    assert s.backend_url == "override"
    assert s.api_key == "key2"
