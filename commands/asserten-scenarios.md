---
description: Outcome dashboard — scenario tiles with status from the latest eval.
---

# /asserten-scenarios

The outcome dashboard surface. Lists every non-skipped test case as a
scenario tile, with its status from the most recent eval run:

- ✓ **passed** — agent handled it correctly
- ✗ **failed** — at least one assertion failed (failure_origin tells you whether agent / env / judge / orchestrator caused it)
- ? **judge_error** — the semantic judge melted down; we don't know if the agent passed or failed
- · **not_yet_evaluated** — case exists but no eval has run yet for this version

Approved cases (🔒) are listed first, so the customer's guaranteed set
is visible at a glance.

## Usage

```bash
echo '{"target": "v1"}' | "${CLAUDE_PLUGIN_ROOT}/bin/asserten-cli" scenarios
```

By default targets v1. Pass `target=v0|v1|v2a|v2b` to scope.

## What you do

1. Invoke the CLI with the target.
2. Show the markdown table output as-is.
3. Suggest follow-ups based on what you see:
   - If passing cases are not approved → suggest `/asserten-approve <ids>`
   - If failed cases dominate → suggest `/asserten-audit` for new patches, or `/asserten-byoe` to add cases that exercise the failure path
   - If many `judge_error` → suggest re-running eval (infra noise, not agent regression)

## Notes

- Each tile shows: scenario name, status glyph, tags, failure_origin.
- Skipped cases are intentionally hidden — they're not running in eval, so they have no status to render. Surface them via `/asserten-status` if needed.
