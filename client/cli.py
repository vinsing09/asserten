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
    render_eval_summary, render_gate_result, render_optimize_result,
    render_scenarios_table, render_session_summary,
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


def _resolve_target_version(state: SessionState, target: str | None) -> tuple[str, str]:
    """Map target alias ('v0' | 'v1' | 'v2a' | 'v2b') to (label, version_id).

    Defaults to v1 since user-provided test cases most often anchor on v1.
    Raises ValueError on unresolvable target.
    """
    tgt = (target or "v1").strip().lower()
    mapping = {
        "v0": state.v0_version_id,
        "v1": state.v1_version_id,
        "v2a": state.v2a_version_id,
        "v2b": state.v2b_version_id,
    }
    if tgt not in mapping:
        raise ValueError(f"unknown target {tgt!r}; expected v0|v1|v2a|v2b")
    vid = mapping[tgt]
    if not vid:
        raise ValueError(f"no {tgt} in session — run prior steps first")
    return tgt, vid


def _record_test_case_op(op: str, target: str, result: dict) -> None:
    """Persist the full result blob of an add/skip/unskip op to session state
    for later inspection via `/asserten-status` when something behaved
    unexpectedly. Captures the WHOLE response (inserted/errors/skipped/
    not_found/unskipped), not just summary counts — forensics needs the rows.
    """
    from datetime import datetime, timezone
    record = {
        "op": op,
        "target": target,
        "at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    update_session(last_test_case_op=record)


def cmd_add_tests(args: dict) -> str:
    """args: {file: <path-to-test-cases-json>} OR raw json body.

    The test cases JSON may be a single object {test_cases: [...]} OR a bare
    list of test cases. Default target version is v1 (most common anchor).
    Pass target="v0"/"v2a"/"v2b" to attach to a different version.
    """
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    # Load test cases — from file if given, else from inline JSON args.
    cases: list[dict] = []
    if "file" in args:
        try:
            with open(args["file"]) as fh:
                payload = json.load(fh)
        except FileNotFoundError:
            return f"⚠ File not found: {args['file']}"
        except json.JSONDecodeError as exc:
            return f"⚠ Invalid JSON in {args['file']}: {exc}"
        cases = payload.get("test_cases", payload) if isinstance(payload, dict) else payload
    elif "test_cases" in args:
        cases = args["test_cases"]
    elif "_raw" in args:
        return ("Pass either `{\"file\": \"path/to/tests.json\"}` or "
                "`{\"test_cases\": [...]}`. Each case needs scenario, input_text, "
                "tool_stubs, assertions, tags.")
    else:
        return "No test cases provided. Pass `file` or `test_cases`."

    if not isinstance(cases, list) or not cases:
        return "Test cases must be a non-empty list."

    target_alias = args.get("target") or "v1"
    try:
        _, vid = _resolve_target_version(state, target_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    c = _client(state)
    result = c.add_user_test_cases(state.agent_id, vid, cases)
    _record_test_case_op("add", target_alias, result)

    n_inserted = len(result.get("inserted", []))
    n_errors = len(result.get("errors", []))
    warnings = [w for entry in result.get("inserted", [])
                for w in entry.get("warnings", [])]

    lines = [f"**Added {n_inserted} test case(s) to {target_alias}**"]
    if n_errors:
        lines.append(f"\n⚠ {n_errors} case(s) rejected:")
        for e in result["errors"]:
            lines.append(f"  - case #{e.get('index','?')} ({e.get('scenario','?')}): "
                         f"{e.get('error','unknown')}")
    if warnings:
        lines.append(f"\n⚠ warnings (non-fatal):")
        for w in warnings[:10]:
            lines.append(f"  - {w}")
    if n_inserted:
        lines.append(f"\nIDs: " + ", ".join(
            f"`{x['id'][:8]}`" for x in result['inserted']
        ))
        lines.append("\nNext: `/asserten-eval v1` to run including your cases.")
    lines.append("\n_Full per-case result saved in session for forensics — see `/asserten-status`._")
    return "\n".join(lines)


def cmd_skip_tests(args: dict) -> str:
    """args: {test_case_ids: [...]} or raw comma-separated ids."""
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    ids = args.get("test_case_ids") or []
    if not ids and "_raw" in args:
        ids = [x.strip() for x in args["_raw"].split(",") if x.strip()]
    if not ids:
        return ("Pass `test_case_ids` (a list) or a comma-separated list of "
                "test-case ids to skip.")

    target_alias = args.get("target") or "v1"
    try:
        _, vid = _resolve_target_version(state, target_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    c = _client(state)
    result = c.skip_test_cases(state.agent_id, vid, ids)
    _record_test_case_op("skip", target_alias, result)

    skipped = result.get("skipped", [])
    nf = result.get("not_found", [])
    lines = [f"**Skipped {len(skipped)} case(s)**"]
    if skipped:
        lines.append("  " + ", ".join(f"`{x[:8]}`" for x in skipped))
    if nf:
        lines.append(f"\n⚠ {len(nf)} id(s) not found on this version:")
        lines.append("  " + ", ".join(f"`{x[:8]}`" for x in nf))
    return "\n".join(lines)


def cmd_unskip_tests(args: dict) -> str:
    """args: {test_case_ids: [...]} or raw comma-separated ids."""
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    ids = args.get("test_case_ids") or []
    if not ids and "_raw" in args:
        ids = [x.strip() for x in args["_raw"].split(",") if x.strip()]
    if not ids:
        return ("Pass `test_case_ids` or a comma-separated list of ids to "
                "un-skip.")

    target_alias = args.get("target") or "v1"
    try:
        _, vid = _resolve_target_version(state, target_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    c = _client(state)
    result = c.unskip_test_cases(state.agent_id, vid, ids)
    _record_test_case_op("unskip", target_alias, result)

    unskipped = result.get("unskipped", [])
    nf = result.get("not_found", [])
    lines = [f"**Un-skipped {len(unskipped)} case(s)**"]
    if unskipped:
        lines.append("  " + ", ".join(f"`{x[:8]}`" for x in unskipped))
    if nf:
        lines.append(f"\n⚠ {len(nf)} id(s) not found:")
        lines.append("  " + ", ".join(f"`{x[:8]}`" for x in nf))
    return "\n".join(lines)


def cmd_byoe(args: dict) -> str:
    """args: {file: <path>} OR {test_cases: [{...}]} OR raw json body.

    BYOE — customer-friendly test-case entry. Accepts the simple shape:
      {input, agent_should_say[], agent_should_call[], agent_should_not[]}

    The interactive walk-through (one field at a time) lives in the slash
    command markdown (commands/asserten-byoe.md) which gathers the fields
    from the user and feeds them as JSON to this CLI. The CLI itself only
    handles the file-or-JSON input shape.
    """
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    cases: list[dict] = []
    if "file" in args:
        try:
            with open(args["file"]) as fh:
                payload = json.load(fh)
        except FileNotFoundError:
            return f"⚠ File not found: {args['file']}"
        except json.JSONDecodeError as exc:
            return f"⚠ Invalid JSON in {args['file']}: {exc}"
        cases = payload.get("test_cases", payload) if isinstance(payload, dict) else payload
    elif "test_cases" in args:
        cases = args["test_cases"]
    elif "_raw" in args:
        return ("Pass `{\"file\": \"path/to/byoe.json\"}` or "
                "`{\"test_cases\": [{input, agent_should_say, agent_should_call, "
                "agent_should_not}, ...]}`.")
    else:
        return "No test cases provided. Pass `file` or `test_cases`."

    if not isinstance(cases, list) or not cases:
        return "Test cases must be a non-empty list."

    target_alias = args.get("target") or "v1"
    try:
        _, vid = _resolve_target_version(state, target_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    c = _client(state)
    result = c.add_byoe_test_cases(state.agent_id, vid, cases)
    _record_test_case_op("byoe", target_alias, result)

    n_inserted = len(result.get("inserted", []))
    n_errors = len(result.get("errors", []))
    fallbacks = [e for e in result.get("inserted", []) if e.get("fallback_reason")]

    lines = [f"**Added {n_inserted} BYOE test case(s) to {target_alias}**"]
    if n_errors:
        lines.append(f"\n⚠ {n_errors} case(s) rejected:")
        for e in result["errors"]:
            lines.append(f"  - case #{e.get('index','?')} ({e.get('input','?')[:60]!r}): "
                         f"{e.get('error','unknown')}")
    if fallbacks:
        lines.append(f"\n⚠ {len(fallbacks)} case(s) used deterministic fallback "
                     "(LLM enrichment failed):")
        for f in fallbacks:
            lines.append(f"  - `{f['id'][:8]}`: {f.get('fallback_reason','unknown')[:120]}")
    if n_inserted:
        lines.append(f"\nScenarios:")
        for entry in result["inserted"][:10]:
            lines.append(f"  - `{entry['id'][:8]}`: {entry['scenario'][:120]}")
        if n_inserted > 10:
            lines.append(f"  ...and {n_inserted - 10} more")
        lines.append("\nNext: `/asserten-eval v1` to run including your BYOE cases.")
    lines.append("\n_Full per-case result saved in session for forensics — see `/asserten-status`._")
    return "\n".join(lines)


def cmd_show_contract(args: dict) -> str:
    """Show the customer's contract with auto-injection transparency.

    Surfaces:
      - Total obligations / forbidden_behaviors / tool_sequences counts.
      - Per-category coverage (and which were auto-injected vs LLM-produced).
      - Specifically calls out the four mandate categories
        (GOAL_COMPLETION, REASONING_QUALITY, ESCALATION, HALLUCINATION_GUARD)
        and whether each was met by the LLM or backfilled as a placeholder.

    Default target is v1 (the current working version). Pass target=v0/v2a/v2b
    to inspect a different version.
    """
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    target_alias = args.get("target") or args.get("_raw") or "v1"
    target_alias = target_alias.strip().lower() if isinstance(target_alias, str) else "v1"
    try:
        _, vid = _resolve_target_version(state, target_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    c = _client(state)
    try:
        contract = c.get_contract(state.agent_id, vid)
    except AssertenError as exc:
        if exc.status == 404:
            return f"No contract found for {target_alias}. Run `/asserten-prepare-eval` to generate one."
        raise

    obls = contract.get("obligations") or []
    forb = contract.get("forbidden_behaviors") or []
    tool_seqs = contract.get("tool_sequences") or []

    # Per-category obligation count + auto-injected count
    from collections import Counter
    obl_total = Counter(o.get("failure_category", "?") for o in obls)
    obl_injected = Counter(
        o.get("failure_category", "?") for o in obls if o.get("auto_injected")
    )
    forb_total = Counter(f.get("failure_category", "?") for f in forb)

    lines = [f"**Contract for {target_alias}** (`{vid[:8]}`)"]
    lines.append("")
    lines.append(f"- {len(obls)} obligation(s)")
    lines.append(f"- {len(forb)} forbidden behavior(s)")
    lines.append(f"- {len(tool_seqs)} tool sequence(s)")
    lines.append("")

    # Mandate-coverage table — the four categories we enforce by code
    mandates = [
        ("GOAL_COMPLETION",     "≥2"),
        ("REASONING_QUALITY",   "≥2"),
        ("ESCALATION",          "≥1"),
        ("HALLUCINATION_GUARD", "≥1 (obligations OR forbidden_behaviors)"),
    ]
    lines.append("**Mandate coverage:**")
    lines.append("")
    lines.append("| Category | Min | Found | Auto-injected | OK? |")
    lines.append("|---|---|---|---|---|")
    for cat, target in mandates:
        if cat == "HALLUCINATION_GUARD":
            found = obl_total.get(cat, 0) + forb_total.get(cat, 0)
        else:
            found = obl_total.get(cat, 0)
        injected = obl_injected.get(cat, 0)
        # Strip "≥" + digits from `target` to get N
        try:
            min_n = int("".join(ch for ch in target if ch.isdigit())[:1])
        except ValueError:
            min_n = 1
        ok = "✓" if found >= min_n else "✗"
        inj_str = f"{injected}" if injected else "—"
        lines.append(f"| {cat} | {target} | {found} | {inj_str} | {ok} |")
    lines.append("")

    n_injected_total = sum(obl_injected.values())
    if n_injected_total > 0:
        lines.append(f"_{n_injected_total} obligation(s) were auto-injected as "
                     "placeholders because the LLM didn't produce enough coverage "
                     "in those categories. These are honest fallbacks, not LLM "
                     "output — you may want to review and refine them in your "
                     "system prompt before evaluating._")
        lines.append("")
        lines.append("Auto-injected entries:")
        for o in obls:
            if o.get("auto_injected"):
                lines.append(f"- `{o.get('id','?')}` [{o.get('failure_category','?')}]: "
                             f"{(o.get('text','') or '')[:140]}")
    else:
        lines.append("_All obligations were produced by the LLM directly — no "
                     "auto-injected placeholders this run._")

    return "\n".join(lines)


def cmd_compare(args: dict) -> str:
    state = load_session()
    return render_compare_table(state)


# ── 2026-05-29 scenarios + approve + deploy-gate ────────────────────────


def cmd_approve(args: dict) -> str:
    """args: {test_case_ids: [...], target?: v0|v1|v2a|v2b} or raw csv.

    The raw token `all-passing` (or `all_passing`) approves every scenario
    currently green on the target version (resolved via /scenarios)."""
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    raw = (args.get("_raw") or "").strip().lower()
    all_passing = raw in ("all-passing", "all_passing") or args.get("all_passing") is True

    target_alias = args.get("target") or "v1"
    try:
        _, vid = _resolve_target_version(state, target_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    c = _client(state)

    if all_passing:
        view = c.get_scenarios(state.agent_id, vid)
        ids = [t.test_case_id for t in view.scenarios if t.status == "passed"]
        if not ids:
            return (f"No passing scenarios to approve on {target_alias}. "
                    "Run `/asserten-eval` first, or check `/asserten-scenarios` "
                    "to see current statuses.")
    else:
        ids = args.get("test_case_ids") or []
        if not ids and "_raw" in args:
            ids = [x.strip() for x in args["_raw"].split(",") if x.strip()]
        if not ids:
            return ("Pass `test_case_ids` (a list), a comma-separated list of "
                    "test-case ids, or `all-passing` to approve every green "
                    "scenario.")

    result = c.approve_test_cases(state.agent_id, vid, ids)
    _record_test_case_op("approve", target_alias, result)

    # Backend returns `approved` = the full guaranteed set after this call;
    # `already_approved` (⊆ approved) is the no-op subset. Newly-flipped is
    # the difference — report that so the count isn't double-counted.
    approved = result.get("approved", [])
    nf = result.get("not_found", [])
    already = result.get("already_approved", [])
    newly = len(approved) - len(already)
    head = f"**Approved {newly} new case(s)** on {target_alias}"
    if already:
        head += f" — {len(approved)} now in the guaranteed set"
    lines = [head]
    if already:
        lines.append(f"_({len(already)} were already approved — no-op)_")
    if nf:
        lines.append("")
        lines.append(f"⚠ Not found at this version: {', '.join(nf)}")
    lines.append("")
    lines.append("Run `/asserten-deploy-gate` to start enforcing the "
                 "no-regression promise on these.")
    return "\n".join(lines)


def cmd_unapprove(args: dict) -> str:
    """args: {test_case_ids: [...], target?: ...} or raw csv."""
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    ids = args.get("test_case_ids") or []
    if not ids and "_raw" in args:
        ids = [x.strip() for x in args["_raw"].split(",") if x.strip()]
    if not ids:
        return ("Pass `test_case_ids` or a comma-separated list of ids to "
                "unapprove.")

    target_alias = args.get("target") or "v1"
    try:
        _, vid = _resolve_target_version(state, target_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    c = _client(state)
    result = c.unapprove_test_cases(state.agent_id, vid, ids)
    _record_test_case_op("unapprove", target_alias, result)

    # Mirror of approve: `unapproved` is the full set now outside the
    # guaranteed set; `already_unapproved` (⊆ unapproved) is the no-op subset.
    unapproved = result.get("unapproved", [])
    nf = result.get("not_found", [])
    already = result.get("already_unapproved", [])
    newly = len(unapproved) - len(already)
    head = f"**Unapproved {newly} case(s)** on {target_alias}"
    if already:
        head += f" — {len(unapproved)} now outside the guaranteed set"
    lines = [head]
    if already:
        lines.append(f"_({len(already)} were already unapproved — no-op)_")
    if nf:
        lines.append(f"⚠ Not found at this version: {', '.join(nf)}")
    return "\n".join(lines)


def cmd_scenarios(args: dict) -> str:
    """args: {target?: v0|v1|v2a|v2b}."""
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    target_alias = args.get("target") or args.get("_raw") or "v1"
    target_alias = target_alias.strip().lower() if isinstance(target_alias, str) else "v1"
    try:
        _, vid = _resolve_target_version(state, target_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    c = _client(state)
    view = c.get_scenarios(state.agent_id, vid)
    return render_scenarios_table(view)


def cmd_deploy_gate(args: dict) -> str:
    """args: {candidate?: v2b, baseline?: v1|auto}.

    Omit `baseline` (or pass `auto`) to let the backend compare against the
    previous eval'd version automatically."""
    state = load_session()
    if not state.agent_id:
        return "No agent in session. Run `/asserten-ingest` first."

    candidate_alias = args.get("candidate") or "v2b"
    try:
        _, cand_vid = _resolve_target_version(state, candidate_alias)
    except ValueError as exc:
        return f"⚠ {exc}"

    # baseline is optional — None lets the backend auto-resolve it.
    baseline_arg = args.get("baseline")
    base_vid = None
    if baseline_arg and str(baseline_arg).strip().lower() != "auto":
        try:
            _, base_vid = _resolve_target_version(state, baseline_arg)
        except ValueError as exc:
            return f"⚠ {exc}"

    auto_eval = args.get("auto_eval", True)
    strict = args.get("strict", True)

    c = _client(state)
    try:
        result = c.run_deploy_gate(state.agent_id, cand_vid, base_vid,
                                   auto_eval=auto_eval, strict=strict)
    except AssertenError as exc:
        # Backend HTTP 400 (e.g. no eval + auto_eval=false) — surface its message.
        update_session(last_error=str(exc), last_gate_verdict="ERROR")
        return f"⚠ Gate could not run: {exc}"

    # Persist the verdict so `ci` mode (handled in main) can set the exit code.
    update_session(last_gate_verdict=result.verdict)
    return render_gate_result(result)


_DISPATCH = {
    "status": cmd_status,
    "reset": cmd_reset,
    "ingest": cmd_ingest,
    "audit": cmd_audit,
    "select": cmd_select,
    "prepare-eval": cmd_prepare_eval,
    "eval": cmd_eval,
    "add-tests": cmd_add_tests,
    "skip-tests": cmd_skip_tests,
    "unskip-tests": cmd_unskip_tests,
    "byoe": cmd_byoe,
    "show-contract": cmd_show_contract,
    "optimize-light": cmd_optimize_light,
    "optimize-deep": cmd_optimize_deep,
    "compare": cmd_compare,
    "approve": cmd_approve,
    "unapprove": cmd_unapprove,
    "scenarios": cmd_scenarios,
    "deploy-gate": cmd_deploy_gate,
}


def _ci_exit_code(verdict: str) -> int:
    """CI exit code for a deploy-gate verdict: 0 only when the gate is green
    (PASSED / PASSED_NO_APPROVED); 1 for BLOCKED / INCONCLUSIVE / ERROR / unknown
    so a non-green gate fails the pipeline."""
    return 0 if verdict in ("PASSED", "PASSED_NO_APPROVED") else 1


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _DISPATCH:
        print(f"Available subcommands: {', '.join(_DISPATCH)}")
        sys.exit(1)
    sub = sys.argv[1]
    args = _load_args()
    try:
        out = _DISPATCH[sub](args)
        print(out)
    except AssertenError as exc:
        update_session(last_error=str(exc))
        print(f"⚠ HTTP {exc.status} from {exc.url}\n```\n{exc.body[:500]}\n```")
        sys.exit(2)
    except Exception as exc:
        update_session(last_error=f"{type(exc).__name__}: {exc}")
        print(f"⚠ unexpected error in `{sub}`:\n```\n{traceback.format_exc()}\n```")
        sys.exit(3)

    # CI mode: deploy-gate exits non-zero on a non-green verdict.
    if sub == "deploy-gate" and args.get("ci"):
        sys.exit(_ci_exit_code(load_session().last_gate_verdict))


if __name__ == "__main__":
    main()
