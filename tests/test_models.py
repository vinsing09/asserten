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
    # Phase 1a fields default to None / 0 / {} when absent — backwards compat
    assert s.validity_warning is None
    assert s.failure_origin_breakdown == {}
    assert s.non_agent_failure_pct == 0.0


def test_eval_summary_with_validity_fields():
    """Phase 1a upstream-lift: backend may now return failure_origin
    breakdown + validity_warning when >=20% of failures came from non-agent
    origins (env/judge/orchestrator)."""
    s = EvalSummary.from_api({
        "pass_rate": 70, "total": 10, "passed": 7, "failed": 3,
        "invalid": False, "judge_error_rate": 0,
        "validity_warning": "validity_warning: 3/10 results (30%) had non-agent failure_origin",
        "failure_origin_breakdown": {"env": 2, "agent": 1},
        "non_agent_failure_pct": 0.20,
    })
    assert s.validity_warning is not None
    assert "30%" in s.validity_warning
    assert s.failure_origin_breakdown == {"env": 2, "agent": 1}
    assert s.non_agent_failure_pct == 0.20


def test_eval_summary_lineage_roundtrip():
    """Lineage triplet (handoff item 9): kind + version + locked-case count
    must roundtrip from the backend summary so future cross-run comparisons
    can detect kind/test-mix drift."""
    s = EvalSummary.from_api({
        "pass_rate": 95, "total": 13, "passed": 12, "failed": 1,
        "invalid": False, "judge_error_rate": 0,
        "lineage": {
            "agent_kind": "multi_turn",
            "agent_version_id": "ver_abc123",
            "total_cases": 13,
            "locked_cases": 3,
            "run_type": "full",
        },
    })
    assert s.lineage["agent_kind"] == "multi_turn"
    assert s.lineage["agent_version_id"] == "ver_abc123"
    assert s.lineage["locked_cases"] == 3


def test_eval_summary_lineage_defaults_to_empty_when_absent():
    """Backwards-compat: a backend that doesn't return `lineage` yet should
    not crash parsing — the field defaults to an empty dict."""
    s = EvalSummary.from_api({
        "pass_rate": 80, "total": 10, "passed": 8, "failed": 2,
    })
    assert s.lineage == {}


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
