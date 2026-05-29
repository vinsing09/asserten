"""Render helpers for asserten slash command output.

Plain-text + markdown — slash commands emit these to the Claude Code chat.
Keep ANSI/colors out so the same output reads cleanly in a future web UI.
"""
from __future__ import annotations

from client.models import (
    EvalSummary, GateResult, OptimizeResult, Patch,
    ScenariosView, SessionState,
)


def render_audit_patches(patches: list[Patch]) -> str:
    """Numbered list + selection prompt. Decision 2B: always all."""
    if not patches:
        return "No patches suggested. Either the agent is clean or the audit failed."
    lines = ["**Suggested patches:**", ""]
    for i, p in enumerate(patches, 1):
        sev = f"[{p.severity}] " if p.severity else ""
        lines.append(f"{i}. {sev}**{p.title}**")
        if p.description:
            lines.append(f"   {p.description[:300]}")
        if p.target_slot:
            lines.append(f"   _slot: {p.target_slot}_")
        lines.append("")
    lines.append("---")
    lines.append("**Which patches to keep?** Reply with comma-separated numbers "
                 "(e.g. `1,3,5`) or `all` to accept everything, or `none` to skip.")
    return "\n".join(lines)


def parse_patch_selection(answer: str, n_patches: int) -> list[int]:
    """Parse user's reply to `render_audit_patches`. Returns 0-based indices.

    Accepts: 'all', 'none', '1,3,5', '1, 3, 5', '1 3 5'. Indices out of range
    are silently dropped.
    """
    a = answer.strip().lower()
    if a in ("all", "*"):
        return list(range(n_patches))
    if a in ("none", "skip", ""):
        return []
    indices: list[int] = []
    for tok in a.replace(",", " ").split():
        try:
            i = int(tok) - 1
            if 0 <= i < n_patches and i not in indices:
                indices.append(i)
        except ValueError:
            continue
    return indices


def render_eval_summary(label: str, summary: EvalSummary) -> str:
    if summary.invalid:
        return (f"**{label}: INVALID** — judge_error_rate "
                f"{summary.judge_error_rate:.0%}. Re-run.")
    if summary.pass_rate is None:
        base = f"**{label}: pending** (no pass_rate yet, total={summary.total})"
    else:
        base = (f"**{label}:** {summary.pass_rate:.0f}% pass "
                f"({summary.passed}/{summary.total}, judge_err "
                f"{summary.judge_error_rate:.0%})")
    if summary.validity_warning:
        # >=20% of results were infra failures (env/judge/orchestrator). The
        # pass_rate is still shown but the operator needs to know it's
        # standing on shaky ground.
        breakdown = summary.failure_origin_breakdown or {}
        breakdown_str = ", ".join(f"{k}={v}" for k, v in sorted(breakdown.items()))
        base += f"\n> ⚠ {summary.validity_warning} (origins: {breakdown_str})"
    return base


def render_optimize_result(r: OptimizeResult) -> str:
    pr = "n/a" if r.pass_rate is None else f"{r.pass_rate:.0f}%"
    delta = "n/a" if r.delta_vs_input is None else f"{r.delta_vs_input:+.1f}pp"
    return (f"**{r.mode.upper()} optimize:** chose `{r.chosen_version_id[:8]}` "
            f"@ {pr} ({delta} vs input median), {r.llm_calls_count} LLM calls, "
            f"{r.wall_seconds:.1f}s wall")


def render_compare_table(state: SessionState) -> str:
    """4-way table: v0 / v1 / v2a / v2b."""
    rows = [
        ("v0 (raw)", state.v0_eval_pass_rate, state.v0_version_id),
        ("v1 (audit + selected patches)", state.v1_eval_pass_rate, state.v1_version_id),
        ("v2a (LIGHT optimize)", state.v2a_eval_pass_rate, state.v2a_version_id),
        ("v2b (DEEP optimize)", state.v2b_eval_pass_rate, state.v2b_version_id),
    ]
    v0 = state.v0_eval_pass_rate
    lines = ["| version | pass_rate | Δ vs v0 | version_id |",
             "|---|---|---|---|"]
    for label, pr, vid in rows:
        if pr is None:
            pr_s, delta_s = "—", "—"
        else:
            pr_s = f"{pr:.0f}%"
            delta_s = "—" if v0 is None else f"{pr - v0:+.1f}pp"
        vid_s = f"`{vid[:8]}`" if vid else "—"
        lines.append(f"| {label} | {pr_s} | {delta_s} | {vid_s} |")
    return "\n".join(lines)


def render_session_summary(state: SessionState) -> str:
    if not state.agent_id:
        return "No active session. Start with `/asserten-ingest`."
    parts = [f"**Active session:** agent `{state.agent_id[:8]}` "
             f"({state.agent_name or 'unnamed'}) on `{state.backend_url}`"]
    if state.v0_version_id:
        parts.append(f"v0 = `{state.v0_version_id[:8]}` "
                     f"pr={state.v0_eval_pass_rate}")
    if state.v1_version_id:
        parts.append(f"v1 = `{state.v1_version_id[:8]}` "
                     f"pr={state.v1_eval_pass_rate}")
    if state.v2a_version_id:
        parts.append(f"v2a = `{state.v2a_version_id[:8]}` "
                     f"pr={state.v2a_eval_pass_rate}")
    if state.v2b_version_id:
        parts.append(f"v2b = `{state.v2b_version_id[:8]}` "
                     f"pr={state.v2b_eval_pass_rate}")
    if state.last_error:
        parts.append(f"⚠ last error: {state.last_error[:200]}")
    if state.last_test_case_op:
        op = state.last_test_case_op
        op_name = op.get("op", "?")
        n_in = len(op.get("inserted") or [])
        n_sk = len(op.get("skipped") or [])
        n_un = len(op.get("unskipped") or [])
        n_err = len(op.get("errors") or [])
        n_nf = len(op.get("not_found") or [])
        summary_bits = []
        if n_in: summary_bits.append(f"inserted={n_in}")
        if n_sk: summary_bits.append(f"skipped={n_sk}")
        if n_un: summary_bits.append(f"unskipped={n_un}")
        if n_err: summary_bits.append(f"errors={n_err}")
        if n_nf: summary_bits.append(f"not_found={n_nf}")
        parts.append(f"last test-case op: `{op_name}` on {op.get('target','?')} "
                     f"at {op.get('at','?')[:19]} — " + ", ".join(summary_bits))
    return "\n".join(parts)


# ── 2026-05-29 scenarios + deploy-gate ──────────────────────────────────


_STATUS_GLYPH = {
    "passed": "✓",
    "failed": "✗",
    "judge_error": "?",
    "not_yet_evaluated": "·",
    "unknown": "·",
}


def render_scenarios_table(view: ScenariosView) -> str:
    """Markdown table view of scenario tiles. Approved cases listed first
    with a 🔒 marker so the customer sees their guaranteed set at a glance."""
    if not view.scenarios:
        return ("No scenarios yet. Generate test cases first via "
                "`/asserten-audit` + `/asserten-select`, then re-run.")
    s = view.summary or {}
    header = [
        f"**Scenarios for version `{view.version_id[:12]}`** "
        f"(latest eval: `{(view.latest_run_id or 'none')[:12]}`)",
        f"- total: {s.get('total', 0)} · "
        f"approved: {s.get('approved', 0)} "
        f"(passing {s.get('approved_passing', 0)} / "
        f"failing {s.get('approved_failing', 0)}) · "
        f"not-yet-eval: {s.get('not_yet_evaluated', 0)}",
        "",
        "| | scenario | status | tags | origin |",
        "|---|---|---|---|---|",
    ]
    rows: list[str] = []
    sorted_tiles = sorted(
        view.scenarios,
        key=lambda t: (
            not t.approved,
            {"failed": 0, "judge_error": 1, "not_yet_evaluated": 2,
             "passed": 3, "unknown": 4}.get(t.status, 5),
            t.scenario_name,
        ),
    )
    for t in sorted_tiles:
        approved_marker = "🔒" if t.approved else ""
        glyph = _STATUS_GLYPH.get(t.status, "·")
        status_cell = f"{glyph} {t.status}"
        tags = ", ".join(t.tags) if t.tags else "—"
        origin = t.failure_origin or "—"
        scenario = t.scenario_name.replace("|", "\\|")
        rows.append(
            f"| {approved_marker} | `{t.test_case_id[:8]}` {scenario} | "
            f"{status_cell} | {tags} | {origin} |"
        )
    return "\n".join(header + rows)


def render_gate_result(result: GateResult) -> str:
    """Markdown summary of a deploy-gate verdict. BLOCKED puts the
    regression list right after the verdict line so it's impossible
    to miss."""
    verdict_glyph = {
        "PASSED": "✓ PASSED",
        "BLOCKED": "🛑 BLOCKED",
        "PASSED_NO_APPROVED": "⚠ PASSED (no approved scenarios)",
        "INCONCLUSIVE": "🟡 INCONCLUSIVE",
    }.get(result.verdict, result.verdict)

    cand = result.candidate_version_id[:12]
    base = result.baseline_version_id[:12]

    lines = [
        f"**Deploy-gate verdict: {verdict_glyph}**",
        f"candidate `{cand}` vs baseline `{base}` on "
        f"{result.approved_count} approved scenario"
        f"{'s' if result.approved_count != 1 else ''}",
        "",
        f"> {result.reason}",
    ]

    # Eval-invalid banner — the verdict couldn't certify because a judge
    # melted down on one side. Impossible to miss.
    if result.candidate_eval_invalid or result.baseline_eval_invalid:
        sides = []
        if result.candidate_eval_invalid:
            sides.append(f"candidate ({result.candidate_judge_error_rate:.0%})")
        if result.baseline_eval_invalid:
            sides.append(f"baseline ({result.baseline_judge_error_rate:.0%})")
        lines.append("")
        lines.append(f"⚠ Could not certify — judge meltdown on "
                     f"{' and '.join(sides)} judge-error rate. Re-run "
                     f"`/asserten-eval` and gate again.")

    if result.regressions:
        lines.append("")
        lines.append("**Regressions** (these block the deploy):")
        lines.append("| scenario | baseline → candidate | origin | reason |")
        lines.append("|---|---|---|---|")
        for r in result.regressions:
            scenario = (r.get("scenario_name") or "").replace("|", "\\|")
            reason = (r.get("candidate_reason") or "")[:80]
            reason = reason.replace("|", "\\|")
            lines.append(
                f"| {scenario} | "
                f"{r.get('baseline_status', '?')} → "
                f"{r.get('candidate_status', '?')} | "
                f"{r.get('failure_origin') or '—'} | {reason} |"
            )

    if result.judge_inconclusive:
        lines.append("")
        lines.append("**Could not be evaluated** (judge error — re-run eval):")
        lines.append("| scenario | baseline → candidate |")
        lines.append("|---|---|")
        for j in result.judge_inconclusive:
            scenario = (j.get("scenario_name") or "").replace("|", "\\|")
            lines.append(
                f"| {scenario} | {j.get('baseline_status', '?')} → "
                f"{j.get('candidate_status', '?')} |"
            )

    counts: list[str] = []
    if result.improvements:
        counts.append(f"{len(result.improvements)} improvement"
                      f"{'s' if len(result.improvements) != 1 else ''}")
    if result.stable_pass:
        counts.append(f"{len(result.stable_pass)} stable_pass")
    if result.stable_fail:
        counts.append(f"{len(result.stable_fail)} stable_fail")
    if result.coverage_gaps:
        counts.append(f"{len(result.coverage_gaps)} coverage_gap"
                      f"{'s' if len(result.coverage_gaps) != 1 else ''}")
    if counts:
        lines.append("")
        lines.append("Other classifications: " + ", ".join(counts))

    return "\n".join(lines)
