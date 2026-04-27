"""CLI dispatcher — slash command markdown files invoke this via
`python -m client.cli <subcommand> [json-args]`. Each subcommand reads
JSON args from stdin (or argv[2]) and prints markdown to stdout.
"""
from __future__ import annotations

import json
import sys
import time
import traceback

from client.api import AssertenClient, AssertenError
from client.format import (
    parse_patch_selection, render_audit_patches, render_compare_table,
    render_eval_summary, render_optimize_result, render_session_summary,
)
from client.models import Patch, SessionState
from client.session import load_session, reset_session, update_session


def _load_args() -> dict:
    """Parse JSON args from argv[2] OR stdin (only when stdin has buffered data).

    Uses select() with a 0.05s timeout to avoid blocking when stdin is
    redirected from /dev/null or a closed pipe but contains no payload.
    Subprocess invocations from slash command markdown explicitly pipe via
    `echo '{...}' | python -m client.cli ...` — those have data ready.
    """
    if len(sys.argv) >= 3:
        raw = sys.argv[2]
    elif not sys.stdin.isatty():
        import select
        # If anything's buffered on stdin within 50ms, read it; otherwise no args.
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        raw = sys.stdin.read().strip() if ready else ""
    else:
        raw = ""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def _client(state: SessionState) -> AssertenClient:
    return AssertenClient(backend_url=state.backend_url, api_key=state.api_key)


def cmd_status(args: dict) -> str:
    return render_session_summary(load_session())


def cmd_reset(args: dict) -> str:
    removed = reset_session()
    return "Session cleared." if removed else "No session to clear."


def cmd_ingest(args: dict) -> str:
    """args: {name, raw_system_prompt, tool_schemas?, business_goal?, desired_behaviors?}"""
    state = load_session()
    c = _client(state)
    draft = c.create_agent_draft(
        name=args.get("name", "unnamed"),
        raw_system_prompt=args.get("raw_system_prompt", ""),
        tool_schemas=args.get("tool_schemas", []),
        business_goal=args.get("business_goal", ""),
        desired_behaviors=args.get("desired_behaviors", []),
    )
    update_session(draft_id=draft["id"], agent_name=args.get("name", ""))
    return (f"**Draft created:** `{draft['id']}`. Next: `/asserten-audit` "
            f"to get patch suggestions.")


def cmd_audit(args: dict) -> str:
    state = load_session()
    if not state.draft_id:
        return "No draft. Run `/asserten-ingest` first."
    c = _client(state)
    report = c.audit_draft(state.draft_id)
    fixes = report.get("suggested_fixes", [])
    update_session(suggested_patches=fixes)
    patches = [Patch.from_api(f) for f in fixes]
    return render_audit_patches(patches)


def cmd_select(args: dict) -> str:
    """args: {answer: 'all' | 'none' | '1,3,5'}

    Single commit produces both v0 ("original") and v1 ("Audited") on
    the same agent automatically. We just look up v0's id from the
    versions list afterwards.
    """
    state = load_session()
    if not state.suggested_patches:
        return "No suggested patches in session. Run `/asserten-audit` first."
    answer = args.get("answer", args.get("_raw", "")).strip()
    if not answer:
        return "Reply with `all`, `none`, or `1,3,5`. Patches still pending."
    indices = parse_patch_selection(answer, len(state.suggested_patches))
    accepted = [state.suggested_patches[i]["id"] for i in indices]

    c = _client(state)
    agent, v1_id = c.commit_draft(state.draft_id, accepted_fix_ids=accepted)
    versions = c.list_versions(agent.id)
    v0_id = next((v.id for v in versions if v.version_number == 0), v1_id)
    update_session(
        agent_id=agent.id, agent_name=agent.name or state.agent_name,
        accepted_patch_ids=accepted, v0_version_id=v0_id, v1_version_id=v1_id,
    )
    fixes_label = ("0 fixes (v1 = v0)" if not accepted
                   else f"{len(accepted)} fixes")
    return (f"**Created:** v0 `{v0_id[:8]}` (raw), "
            f"v1 `{v1_id[:8]}` ({fixes_label}) on agent "
            f"`{agent.id[:8]}`. Next: `/asserten-prepare-eval` then "
            f"`/asserten-eval v0` and `v1`.")


def cmd_prepare_eval(args: dict) -> str:
    """Generate contract + test cases on v1 — required before any eval."""
    state = load_session()
    if not state.v1_version_id:
        return "No v1 yet. Run `/asserten-select` first."
    c = _client(state)
    t0 = time.monotonic()
    contract = c.generate_contract(state.agent_id, state.v1_version_id)
    t1 = time.monotonic()
    tcs = c.generate_test_cases(state.agent_id, state.v1_version_id)
    n_tcs = tcs.get("count") if isinstance(tcs, dict) else 0
    t2 = time.monotonic()
    return (f"**Eval prep complete:**\n"
            f"- contract: {len(contract.get('obligations', []))} obligations "
            f"({t1 - t0:.1f}s)\n"
            f"- test cases: {n_tcs} generated ({t2 - t1:.1f}s)\n\n"
            f"Now run `/asserten-eval v0` and `/asserten-eval v1`.")


def cmd_eval(args: dict) -> str:
    """args: {target: 'v0'|'v1'|'v2a'|'v2b'}"""
    state = load_session()
    target = (args.get("target") or args.get("_raw") or "v0").strip().lower()
    field_map = {
        "v0": ("v0_version_id", "v0_eval_pass_rate"),
        "v1": ("v1_version_id", "v1_eval_pass_rate"),
        "v2a": ("v2a_version_id", "v2a_eval_pass_rate"),
        "v2b": ("v2b_version_id", "v2b_eval_pass_rate"),
    }
    if target not in field_map:
        return f"Unknown target `{target}`. Use one of: v0, v1, v2a, v2b."
    vid_field, pr_field = field_map[target]
    vid = getattr(state, vid_field, "")
    if not vid:
        return f"No `{target}` version in session yet."
    c = _client(state)
    src = state.v0_version_id if target != "v0" else None
    summary = c.run_eval(state.agent_id, vid, test_case_source_version_id=src)
    update_session(**{pr_field: summary.pass_rate})
    return render_eval_summary(target, summary)


def cmd_optimize_light(args: dict) -> str:
    state = load_session()
    if not state.candidate_v1_ids:
        return ("No candidate v1 ids in session. Populate "
                "`candidate_v1_ids` (rerun `/asserten-audit-bulk` once it "
                "ships, or set them manually for v0.1).")
    c = _client(state)
    r = c.optimize_light(state.agent_id, state.candidate_v1_ids)
    update_session(v2a_version_id=r.chosen_version_id,
                   v2a_eval_pass_rate=r.pass_rate)
    return render_optimize_result(r)


def cmd_optimize_deep(args: dict) -> str:
    state = load_session()
    if not state.v1_version_id:
        return "No v1. Run `/asserten-select` first."
    eval_run_id = args.get("eval_run_id", "")
    if not eval_run_id:
        return "Pass `eval_run_id` from `/asserten-eval v1`."
    c = _client(state)
    job = c.optimize_deep(state.agent_id, state.v1_version_id, eval_run_id)
    job_id = job.get("job_id", "")
    if not job_id:
        return f"No job_id returned: {job}"
    final = c.wait_improvement_job(job_id, poll_seconds=30, max_seconds=1800)
    status = final.get("status", "unknown")
    attempt_n = state.v2b_attempts + 1

    if status != "completed":
        update_session(v2b_attempts=attempt_n, v2b_last_status=status)
        return (f"**Deep optimisation attempt #{attempt_n}:** job `{job_id[:8]}` "
                f"ended with status `{status}`. Try `/asserten-optimize-deep` "
                f"again, or check backend logs.")

    suggestions = final.get("suggestions") or []
    if not suggestions:
        update_session(v2b_attempts=attempt_n, v2b_last_status="no_valid_patch")
        return (f"**Deep optimisation attempt #{attempt_n}:** couldn't produce "
                f"a valid patch — every candidate was dropped at verify because "
                f"it would have regressed an existing assertion. v2b unavailable "
                f"for this run. You can `/asserten-optimize-deep` again to retry "
                f"with a fresh sample (each run is non-deterministic).")

    # Apply the surviving patches to create v2b.
    fix_ids = [s.get("id") for s in suggestions if s.get("id")]
    structured = [
        {
            "id": s.get("id"),
            "target_slot": s.get("target_slot"),
            "tool_filter": s.get("tool_filter", "all"),
            "on_error_only": s.get("on_error_only", False),
            "prompt_patch": s.get("prompt_patch", ""),
        }
        for s in suggestions
    ]
    try:
        v2b_id = c.apply_improvements(
            state.agent_id, state.v1_version_id,
            accepted_fix_ids=fix_ids, eval_run_id=eval_run_id,
            accepted_structured=structured,
        )
    except Exception as exc:
        update_session(v2b_attempts=attempt_n, v2b_last_status="apply_failed")
        return (f"**Deep optimisation attempt #{attempt_n}:** {len(suggestions)} "
                f"patches survived verify but apply failed: "
                f"`{type(exc).__name__}: {exc}`.")

    update_session(v2b_version_id=v2b_id, v2b_attempts=attempt_n,
                   v2b_last_status="ok")
    return (f"**Deep optimisation attempt #{attempt_n}:** {len(suggestions)} "
            f"patch(es) applied → v2b `{v2b_id[:8]}`. "
            f"Run `/asserten-eval v2b`.")


def cmd_compare(args: dict) -> str:
    state = load_session()
    return render_compare_table(state)


_DISPATCH = {
    "status": cmd_status,
    "reset": cmd_reset,
    "ingest": cmd_ingest,
    "audit": cmd_audit,
    "select": cmd_select,
    "prepare-eval": cmd_prepare_eval,
    "eval": cmd_eval,
    "optimize-light": cmd_optimize_light,
    "optimize-deep": cmd_optimize_deep,
    "compare": cmd_compare,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _DISPATCH:
        print(f"Available subcommands: {', '.join(_DISPATCH)}")
        sys.exit(1)
    sub = sys.argv[1]
    try:
        out = _DISPATCH[sub](_load_args())
        print(out)
    except AssertenError as exc:
        update_session(last_error=str(exc))
        print(f"⚠ HTTP {exc.status} from {exc.url}\n```\n{exc.body[:500]}\n```")
        sys.exit(2)
    except Exception as exc:
        update_session(last_error=f"{type(exc).__name__}: {exc}")
        print(f"⚠ unexpected error in `{sub}`:\n```\n{traceback.format_exc()}\n```")
        sys.exit(3)


if __name__ == "__main__":
    main()
