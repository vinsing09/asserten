"""CLI dispatcher — slash command markdown files invoke this via
`python -m client.cli <subcommand> [json-args]`. Each subcommand reads
JSON args from stdin (or argv[2]) and prints markdown to stdout.
"""
from __future__ import annotations

import json
import sys
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
    """args: {answer: 'all' | 'none' | '1,3,5'}"""
    state = load_session()
    if not state.suggested_patches:
        return "No suggested patches in session. Run `/asserten-audit` first."
    answer = args.get("answer", args.get("_raw", "")).strip()
    if not answer:
        return "Reply with `all`, `none`, or `1,3,5`. Patches still pending."
    indices = parse_patch_selection(answer, len(state.suggested_patches))
    accepted = [state.suggested_patches[i]["id"] for i in indices]
    if not accepted:
        return "No patches selected (treated as `none`). v1 will equal v0."
    c = _client(state)
    agent = c.commit_draft(state.draft_id, accepted_fix_ids=accepted)
    versions = c.list_versions(agent.id)
    v0 = versions[0].id if versions else ""
    update_session(
        agent_id=agent.id, agent_name=agent.name or state.agent_name,
        accepted_patch_ids=accepted, v0_version_id=v0,
    )
    return (f"**v0 committed:** agent `{agent.id[:8]}` ({agent.name}), "
            f"version `{v0[:8]}`, {len(accepted)} patches accepted. "
            f"Next: `/asserten-eval v0`.")


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
        return "No v1 version in session. Run `/asserten-select` first."
    c = _client(state)
    # Look up the most recent eval_run for v1 — needed by /improvements.
    versions = c.list_versions(state.agent_id)
    eval_run_id = args.get("eval_run_id", "")
    if not eval_run_id:
        return ("Pass `eval_run_id` from `/asserten-eval v1` output. "
                "(v0.1 manual lookup; future versions will auto-resolve.)")
    job = c.optimize_deep(state.agent_id, state.v1_version_id, eval_run_id)
    job_id = job.get("job_id", "")
    if not job_id:
        return f"Deep optimize did not return job_id: {job}"
    final = c.wait_improvement_job(job_id, poll_seconds=30, max_seconds=1800)
    update_session(v2b_version_id=final.get("result_version_id", ""))
    return (f"**DEEP optimize:** job `{job_id[:8]}` → status "
            f"`{final.get('status')}`. Run `/asserten-eval v2b` next.")


def cmd_compare(args: dict) -> str:
    state = load_session()
    return render_compare_table(state)


_DISPATCH = {
    "status": cmd_status,
    "reset": cmd_reset,
    "ingest": cmd_ingest,
    "audit": cmd_audit,
    "select": cmd_select,
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
