---
description: Remove test cases from the customer's guaranteed set.
---

# /asserten-unapprove

Inverse of `/asserten-approve`. Removes the cases from the deploy-gate's
guaranteed set, so regressions on them no longer block deploys.

## Inputs

- **List:** `/asserten-unapprove {"test_case_ids": ["id_1", "id_2"]}`
- **Comma-separated:** `/asserten-unapprove id_1, id_2`

By default targets v1. Pass `target=v0|v1|v2a|v2b` to scope.

## What you do

1. Parse user input.
2. Invoke the CLI:

```bash
echo '{"test_case_ids": ["..."], "target": "v1"}' | "${CLAUDE_PLUGIN_ROOT}/bin/asserten-cli" unapprove
```

3. Output reports: `unapproved`, `not_found`, `already_unapproved`.
