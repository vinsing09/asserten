"""cmd_prepare_eval — the test-case `count` knob is now configurable from the
client (backend default 40 when omitted; 1–100 when set)."""
from __future__ import annotations

import pytest

from client.cli import cmd_prepare_eval
from client.models import SessionState
from client.session import save_session


@pytest.fixture
def session_v1(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(tmp_path / "s.json"))
    save_session(SessionState(backend_url="http://x", api_key="k",
                              agent_id="a1", v1_version_id="v1id"))


class _Stub:
    def __init__(self):
        self.count = "UNSET"

    def generate_contract(self, agent_id, version_id):
        return {"obligations": [1, 2]}

    def generate_test_cases(self, agent_id, version_id, count=None):
        self.count = count
        return {"count": count if count is not None else 40}


def _patch(monkeypatch, stub):
    import client.cli
    monkeypatch.setattr(client.cli, "_client", lambda _s: stub)


def test_prepare_eval_default_omits_count(session_v1, monkeypatch):
    stub = _Stub(); _patch(monkeypatch, stub)
    out = cmd_prepare_eval({})
    assert stub.count is None              # None → backend default
    assert "backend default" in out


def test_prepare_eval_forwards_explicit_count(session_v1, monkeypatch):
    stub = _Stub(); _patch(monkeypatch, stub)
    out = cmd_prepare_eval({"count": 75})
    assert stub.count == 75
    assert "requested 75" in out


def test_prepare_eval_accepts_raw_digit(session_v1, monkeypatch):
    stub = _Stub(); _patch(monkeypatch, stub)
    cmd_prepare_eval({"_raw": "50"})
    assert stub.count == 50


def test_prepare_eval_rejects_out_of_range(session_v1, monkeypatch):
    stub = _Stub(); _patch(monkeypatch, stub)
    out = cmd_prepare_eval({"count": 500})
    assert "between 1 and 100" in out
    assert stub.count == "UNSET"           # never called the backend


def test_prepare_eval_rejects_non_integer(session_v1, monkeypatch):
    stub = _Stub(); _patch(monkeypatch, stub)
    out = cmd_prepare_eval({"count": "abc"})
    assert "must be an integer" in out
