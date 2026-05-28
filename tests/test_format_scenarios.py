"""Unit tests for render_scenarios_table — pure render function.

Pass a ScenariosView directly, assert on markdown structure: header line,
summary counts, status glyphs, the 🔒 approved marker, approved-first
ordering, tag rendering, and pipe-escaping in scenario names.
"""
from __future__ import annotations

from client.format import render_scenarios_table
from client.models import ScenarioTile, ScenariosView


def _view(tiles, summary=None) -> ScenariosView:
    return ScenariosView(
        version_id="v1id1234abcd", latest_run_id="run_abcd1234",
        scenarios=tiles, summary=summary or {})


def test_empty_view_returns_guidance():
    out = render_scenarios_table(_view([]))
    assert "No scenarios yet" in out


def test_header_and_summary_line():
    view = _view(
        [ScenarioTile(test_case_id="tc1", scenario_name="A", status="passed")],
        summary={"total": 5, "approved": 2, "approved_passing": 1,
                 "approved_failing": 1, "not_yet_evaluated": 1})
    out = render_scenarios_table(view)
    assert "Scenarios for version `v1id1234abcd`" in out
    assert "latest eval: `run_abcd1234`" in out
    assert "total: 5" in out
    assert "approved: 2" in out
    assert "passing 1" in out and "failing 1" in out
    assert "not-yet-eval: 1" in out


def test_status_glyphs_render():
    tiles = [
        ScenarioTile(test_case_id="t_p", scenario_name="pass case", status="passed"),
        ScenarioTile(test_case_id="t_f", scenario_name="fail case", status="failed"),
        ScenarioTile(test_case_id="t_j", scenario_name="judge case", status="judge_error"),
        ScenarioTile(test_case_id="t_n", scenario_name="new case", status="not_yet_evaluated"),
    ]
    out = render_scenarios_table(_view(tiles))
    assert "✓ passed" in out
    assert "✗ failed" in out
    assert "? judge_error" in out
    assert "· not_yet_evaluated" in out


def test_approved_listed_first_with_lock_marker():
    tiles = [
        ScenarioTile(test_case_id="t_unapp", scenario_name="not approved",
                     approved=False, status="passed"),
        ScenarioTile(test_case_id="t_app", scenario_name="approved one",
                     approved=True, status="failed"),
    ]
    out = render_scenarios_table(_view(tiles))
    assert "🔒" in out
    # approved (failed) row must appear before the unapproved (passed) row
    assert out.index("approved one") < out.index("not approved")


def test_tags_and_origin_columns():
    tiles = [ScenarioTile(test_case_id="t1", scenario_name="x",
                          tags=["happy_path", "edge"], status="failed",
                          failure_origin="env")]
    out = render_scenarios_table(_view(tiles))
    assert "happy_path, edge" in out
    assert "env" in out


def test_no_tags_renders_dash():
    tiles = [ScenarioTile(test_case_id="t1", scenario_name="x", tags=[],
                          status="passed")]
    out = render_scenarios_table(_view(tiles))
    # tags + origin both fall back to em-dash
    assert "—" in out


def test_pipe_in_scenario_name_escaped():
    tiles = [ScenarioTile(test_case_id="t1", scenario_name="a | b table-breaker",
                          status="passed")]
    out = render_scenarios_table(_view(tiles))
    assert "a \\| b table-breaker" in out
