---
description: Re-include previously-skipped test cases in eval runs.
---

# /asserten-unskip-tests

Inverse of `/asserten-skip-tests`. Re-enables one or more skipped cases so
they run again in eval.

## Inputs

- **List:** `/asserten-unskip-tests {"test_case_ids": ["id_1", "id_2"]}`
- **Comma-separated:** `/asserten-unskip-tests id_1, id_2`

By default targets v1. Pass `target=v0|v1|v2a|v2b` to scope.

## What you do

1. Parse the user's input.
2. Invoke the CLI:

```bash
echo '{"test_case_ids": ["id_1"]}' | python -m client.cli unskip-tests
```

3. Show how many were un-skipped + any IDs not found.
