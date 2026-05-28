"""Unit tests for render_gate_result — pure render function.

Pass a GateResult directly, assert on markdown structure: verdict glyph,
candidate/baseline line, regression table (only when regressions exist),
pluralisation, other-classification counts, and pipe-escaping.
"""
from __future__ import annotations

from client.format import render_gate_result
from client.models import GateResult


def _gate(**kw) -> GateResult:
    base = dict(verdict="PASSED", candidate_version_id="candABCD1234",
                baseline_version_id="baseEFGH5678", approved_count=0,
                regressions=[], improvements=[], stable_pass=[],
                stable_fail=[], coverage_gaps=[], reason="ok")
    base.update(kw)
    return GateResult(**base)


def test_passed_verdict_glyph_and_line():
    out = render_gate_result(_gate(verdict="PASSED", approved_count=3,
                                   reason="No regressions."))
    assert "✓ PASSED" in out
    assert "candidate `candABCD1234`" in out
    assert "baseline `baseEFGH5678`" in out
    assert "3 approved scenarios" in out
    assert "No regressions." in out


def test_singular_scenario_phrasing_for_one():
    out = render_gate_result(_gate(approved_count=1))
    assert "1 approved scenario" in out
    assert "1 approved scenarios" not in out


def test_blocked_renders_regression_table():
    out = render_gate_result(_gate(
        verdict="BLOCKED", approved_count=2,
        regressions=[{
            "test_case_id": "tc_r", "scenario_name": "refund case",
            "baseline_status": "passed", "candidate_status": "failed",
            "failure_origin": "agent", "candidate_reason": "denied valid refund"}],
        reason="1 regressed."))
    assert "🛑 BLOCKED" in out
    assert "Regressions" in out and "block the deploy" in out
    assert "refund case" in out
    assert "passed → failed" in out
    assert "agent" in out
    assert "denied valid refund" in out


def test_passed_has_no_regression_table():
    out = render_gate_result(_gate(verdict="PASSED", approved_count=2,
                                   stable_pass=[{"a": 1}, {"b": 2}]))
    assert "Regressions" not in out


def test_other_classification_counts():
    out = render_gate_result(_gate(
        verdict="PASSED", approved_count=5,
        improvements=[{"a": 1}],
        stable_pass=[{"a": 1}, {"b": 2}],
        stable_fail=[{"c": 3}],
        coverage_gaps=[{"d": 4}, {"e": 5}]))
    assert "1 improvement" in out
    assert "2 stable_pass" in out
    assert "1 stable_fail" in out
    assert "2 coverage_gaps" in out


def test_passed_no_approved_verdict_label():
    out = render_gate_result(_gate(
        verdict="PASSED_NO_APPROVED", approved_count=0,
        reason="No approved scenarios."))
    assert "PASSED (no approved scenarios)" in out


def test_regression_reason_truncated_and_pipe_escaped():
    long_reason = "x | y " + "z" * 200
    out = render_gate_result(_gate(
        verdict="BLOCKED", approved_count=1,
        regressions=[{"scenario_name": "s", "baseline_status": "passed",
                      "candidate_status": "failed", "failure_origin": "agent",
                      "candidate_reason": long_reason}]))
    # reason truncated to 80 chars then pipe-escaped; the pipe is escaped so
    # it can't break the markdown table when rendered.
    assert "x \\| y" in out
    # the row stays on a single line and every pipe in it is escaped (\|),
    # leaving exactly the 5 column-delimiter pipes once escapes are stripped.
    reg_line = [ln for ln in out.splitlines() if "passed → failed" in ln][0]
    assert reg_line.replace("\\|", "").count("|") == 5  # 4 cols -> 5 delimiters
    # truncation: 80-char cap means the 200 z's are cut down, not all present.
    assert "z" * 200 not in reg_line
