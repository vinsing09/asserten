"""Unit tests for cmd_scenarios.

Mocks AssertenClient.get_scenarios to return a ScenariosView (the api layer
already deserialises the backend JSON into the dataclass). Verifies:
  - early-guard branches (no session, bad target)
  - success path: backend called with right (agent, version); table rendered
  - the three statuses, the 🔒 approved marker, and the summary line all appear
"""
from __future__ import annotations

import pytest

from client.cli import cmd_scenarios
from client.models import ScenarioTile, ScenariosView, SessionState
from client.session import save_session


@pytest.fixture
def session_with_v1(tmp_path, monkeypatch):
    sp = tmp_path / "session.json"
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(sp))
    save_session(SessionState(
        backend_url="http://test", api_key="k", agent_id="a1",
        v1_version_id="v1id",
    ))
    return sp


def _three_tile_view() -> ScenariosView:
    return ScenariosView(
        version_id="v1id",
        latest_run_id="run_abc123",
        scenarios=[
            ScenarioTile(test_case_id="tc_pass1", scenario_name="Refund within policy",
                         tags=["happy_path"], approved=True, status="passed"),
            ScenarioTile(test_case_id="tc_fail1", scenario_name="Refund outside policy",
                         tags=["edge"], approved=True, status="failed",
                         failure_origin="agent", reason="agent granted disallowed refund"),
            ScenarioTile(test_case_id="tc_new1", scenario_name="Multi-item return",
                         tags=[], approved=False, status="not_yet_evaluated"),
        ],
        summary={"total": 3, "approved": 2, "approved_passing": 1,
                 "approved_failing": 1, "not_yet_evaluated": 1},
    )


class _StubClient:
    def __init__(self, view: ScenariosView):
        self.view = view
        self.calls: list[tuple] = []

    def get_scenarios(self, agent_id, version_id):
        self.calls.append((agent_id, version_id))
        return self.view


def _patch_client(monkeypatch, stub) -> None:
    import client.cli
    monkeypatch.setattr(client.cli, "_client", lambda _state: stub)


def test_scenarios_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSERTEN_SESSION_PATH", str(tmp_path / "s.json"))
    out = cmd_scenarios({"target": "v1"})
    assert "No agent in session" in out


def test_scenarios_unknown_target(session_with_v1, monkeypatch):
    _patch_client(monkeypatch, _StubClient(_three_tile_view()))
    out = cmd_scenarios({"target": "v99"})
    assert "unknown target" in out


def test_scenarios_success_renders_all_three_statuses(session_with_v1, monkeypatch):
    stub = _StubClient(_three_tile_view())
    _patch_client(monkeypatch, stub)

    out = cmd_scenarios({"target": "v1"})

    # Backend hit with the resolved version
    assert stub.calls[0] == ("a1", "v1id")
    # All three statuses rendered
    assert "passed" in out and "failed" in out and "not_yet_evaluated" in out
    # Approved marker present (🔒) and origin surfaced for the failing case
    assert "🔒" in out
    assert "agent" in out  # failure_origin column
    # Summary line
    assert "approved: 2" in out
    assert "passing 1" in out and "failing 1" in out


def test_scenarios_raw_arg_used_as_target(session_with_v1, monkeypatch):
    stub = _StubClient(_three_tile_view())
    _patch_client(monkeypatch, stub)
    cmd_scenarios({"_raw": "v1"})
    assert stub.calls[0] == ("a1", "v1id")


def test_scenarios_empty_view_message(session_with_v1, monkeypatch):
    empty = ScenariosView(version_id="v1id", latest_run_id=None,
                          scenarios=[], summary={})
    _patch_client(monkeypatch, _StubClient(empty))
    out = cmd_scenarios({"target": "v1"})
    assert "No scenarios yet" in out
