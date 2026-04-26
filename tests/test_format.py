"""Unit tests for client/format.py — render helpers + patch-selection parser."""
import pytest

from client.format import (
    parse_patch_selection,
    render_audit_patches,
    render_compare_table,
    render_eval_summary,
    render_optimize_result,
    render_session_summary,
)
from client.models import EvalSummary, OptimizeResult, Patch, SessionState


# ─── parse_patch_selection ──────────────────────────────────────────────────


def test_parse_all_returns_full_range():
    assert parse_patch_selection("all", 5) == [0, 1, 2, 3, 4]
    assert parse_patch_selection("ALL", 3) == [0, 1, 2]
    assert parse_patch_selection("*", 2) == [0, 1]


def test_parse_none_or_empty_returns_empty():
    assert parse_patch_selection("none", 5) == []
    assert parse_patch_selection("", 5) == []
    assert parse_patch_selection("skip", 5) == []


def test_parse_comma_separated_indices():
    assert parse_patch_selection("1,3,5", 5) == [0, 2, 4]


def test_parse_space_separated_indices():
    assert parse_patch_selection("1 3 5", 5) == [0, 2, 4]


def test_parse_mixed_separators():
    assert parse_patch_selection("1, 3 5", 5) == [0, 2, 4]


def test_parse_drops_out_of_range_indices():
    assert parse_patch_selection("1,7,3", 5) == [0, 2]


def test_parse_dedupes():
    assert parse_patch_selection("1,1,3,3", 5) == [0, 2]


def test_parse_drops_garbage_tokens():
    assert parse_patch_selection("1,foo,3", 5) == [0, 2]


# ─── render_audit_patches ───────────────────────────────────────────────────


def test_render_audit_patches_empty():
    out = render_audit_patches([])
    assert "No patches" in out


def test_render_audit_patches_basic():
    patches = [
        Patch(id="p1", title="Add validate-first guard", description="Prevents bad writes",
              severity="high"),
        Patch(id="p2", title="Confirm refund amount", description="User-facing safety"),
    ]
    out = render_audit_patches(patches)
    assert "1." in out
    assert "Add validate-first guard" in out
    assert "[high]" in out
    assert "Confirm refund amount" in out
    assert "Reply with comma-separated numbers" in out
    assert "`all`" in out


# ─── render_eval_summary ────────────────────────────────────────────────────


def test_render_eval_invalid():
    s = EvalSummary(pass_rate=None, invalid=True, judge_error_rate=0.42)
    out = render_eval_summary("v1", s)
    assert "INVALID" in out
    assert "42%" in out


def test_render_eval_pending():
    s = EvalSummary(pass_rate=None, invalid=False)
    assert "pending" in render_eval_summary("v1", s)


def test_render_eval_normal():
    s = EvalSummary(pass_rate=95.0, total=13, passed=12, judge_error_rate=0.0)
    out = render_eval_summary("v1", s)
    assert "95%" in out
    assert "12/13" in out


# ─── render_optimize_result ─────────────────────────────────────────────────


def test_render_optimize_result_full():
    r = OptimizeResult(mode="light", chosen_version_id="abc12345xyz",
                       pass_rate=95.0, delta_vs_input=3.0,
                       wall_seconds=0.01, llm_calls_count=0)
    out = render_optimize_result(r)
    assert "LIGHT" in out
    assert "abc12345" in out
    assert "95%" in out
    assert "+3.0pp" in out


def test_render_optimize_result_handles_nones():
    r = OptimizeResult(mode="deep", chosen_version_id="xyz",
                       pass_rate=None, delta_vs_input=None,
                       wall_seconds=10.0, llm_calls_count=200)
    out = render_optimize_result(r)
    assert "n/a" in out


# ─── render_compare_table ───────────────────────────────────────────────────


def test_render_compare_table_partial():
    s = SessionState(backend_url="x", v0_eval_pass_rate=85.0,
                     v0_version_id="v0xyz",
                     v1_eval_pass_rate=92.0, v1_version_id="v1xyz")
    out = render_compare_table(s)
    assert "v0 (raw)" in out
    assert "85%" in out
    assert "v1 (audit + selected patches)" in out
    assert "+7.0pp" in out
    # v2a/v2b are dashes
    assert "—" in out


def test_render_compare_table_no_v0_skips_delta():
    s = SessionState(backend_url="x", v1_eval_pass_rate=92.0)
    out = render_compare_table(s)
    # delta column must show — when there's no v0 to compare against
    assert "92%" in out


# ─── render_session_summary ─────────────────────────────────────────────────


def test_render_session_summary_no_session():
    s = SessionState(backend_url="x")
    out = render_session_summary(s)
    assert "No active session" in out


def test_render_session_summary_partial():
    s = SessionState(backend_url="http://x", agent_id="abc12345xyz",
                     agent_name="Support", v0_version_id="v0xyz",
                     v0_eval_pass_rate=85.0)
    out = render_session_summary(s)
    assert "abc12345" in out
    assert "Support" in out
    assert "85.0" in out


def test_render_session_summary_includes_last_error():
    s = SessionState(backend_url="x", agent_id="a", last_error="boom")
    out = render_session_summary(s)
    assert "boom" in out
