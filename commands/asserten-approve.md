---
description: Promote test cases into the customer's guaranteed set — deploy-gate blocks regressions on these.
---

# /asserten-approve

Mark test cases as **approved** — promotes them into the customer's
guaranteed set. The deploy-gate (`/asserten-deploy-gate`) blocks any new
version that regresses on an approved case (pass → fail).

Approval is per (test_case_id, version_id). Promoting a case at v1
doesn't auto-promote its equivalent at v2 — explicit re-approval is the
safe default for v0.1.

## Inputs

- **List:** `/asserten-approve {"test_case_ids": ["id_1", "id_2"]}`
- **Comma-separated:** `/asserten-approve id_1, id_2, id_3`
- **All currently-green:** `/asserten-approve all-passing` — approves every
  scenario whose latest-eval status is `passed` on the target version.

By default targets v1 (most common). Pass `target=v0|v1|v2a|v2b` to scope.

## What you do

1. Parse user input into a list of test_case_ids.
2. Invoke the CLI:

```bash
echo '{"test_case_ids": ["..."], "target": "v1"}' | "${CLAUDE_PLUGIN_ROOT}/bin/asserten-cli" approve
```

3. Show the output as-is. It reports:
   - `approved`: how many cases newly approved
   - `not_found`: any IDs that didn't match a real test case at that version
   - `already_approved`: idempotent no-ops

## Notes

- Approval is **independent of skipped**: a case can be approved + skipped
  (still in the guaranteed set, just not currently running). The deploy
  gate will surface a coverage_gap if a previously-evaluated approved
  case is skipped on the new run.
- Use `/asserten-scenarios` first to see which cases are currently passing
  and worth approving.
- Use `/asserten-unapprove` to remove from the guaranteed set.
