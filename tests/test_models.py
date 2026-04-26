"""Unit tests for client/models.py — dataclass round-trip + from_api parsers."""
import pytest

from client.models import (
    Agent, AgentVersion, EvalSummary, OptimizeResult, Patch, SessionState,
)


def test_agent_from_api_minimum():
    a = Agent.from_api({"id": "x", "name": "n"})
    assert a.id == "x" and a.name == "n"
    assert a.business_goal == ""
    assert a.created_at == ""


def test_agent_version_handles_missing_optional_fields():
    v = AgentVersion.from_api({"id": "v1", "agent_id": "a"})
    assert v.id == "v1" and v.agent_id == "a"
    assert v.version_number == 0
    assert v.label == ""


def test_patch_falls_back_to_issue_when_no_title():
    p = Patch.from_api({
        "id": "fix_1",
        "issue": "Agent does not call validate before processing",
    })
    assert p.title.startswith("Agent does not call validate")


def test_patch_handles_alt_field_names():
    p = Patch.from_api({
        "id": "fix_2",
        "rationale": "validate-first prevents bad-state writes",
        "priority": "high",
    })
    assert p.description == "validate-first prevents bad-state writes"
    assert p.severity == "high"


def test_eval_summary_invalid_flag():
    s = EvalSummary.from_api({"pass_rate": None, "invalid": True,
                              "judge_error_rate": 0.42})
    assert s.invalid is True
    assert s.judge_error_rate == 0.42
    assert s.pass_rate is None


def test_eval_summary_full():
    s = EvalSummary.from_api({"pass_rate": 95, "total": 13, "passed": 12,
                              "failed": 1, "invalid": False,
                              "judge_error_rate": 0})
    assert s.pass_rate == 95
    assert s.total == 13


def test_session_state_round_trip():
    s = SessionState(
        backend_url="http://x", api_key="k", agent_id="a",
        v0_eval_pass_rate=85.0, v1_version_id="vv",
    )
    d = s.to_dict()
    s2 = SessionState.from_dict(d)
    assert s2.backend_url == "http://x"
    assert s2.v0_eval_pass_rate == 85.0


def test_session_state_ignores_unknown_keys():
    """SessionState.from_dict drops fields not in the schema."""
    s = SessionState.from_dict({"backend_url": "x", "garbage_field": 99})
    assert s.backend_url == "x"
    assert not hasattr(s, "garbage_field")


def test_optimize_result_default_extra():
    r = OptimizeResult(mode="light", chosen_version_id="v",
                       pass_rate=95.0, delta_vs_input=3.0,
                       wall_seconds=0.01, llm_calls_count=0)
    assert r.extra == {}
