"""Render helpers for asserten slash command output.

Plain-text + markdown — slash commands emit these to the Claude Code chat.
Keep ANSI/colors out so the same output reads cleanly in a future web UI.
"""
from __future__ import annotations

from client.models import EvalSummary, OptimizeResult, Patch, SessionState


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
        return f"**{label}: pending** (no pass_rate yet, total={summary.total})"
    return (f"**{label}:** {summary.pass_rate:.0f}% pass "
            f"({summary.passed}/{summary.total}, judge_err "
            f"{summary.judge_error_rate:.0%})")


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
    return "\n".join(parts)
