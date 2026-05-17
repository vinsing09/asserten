---
description: Mark generated test cases as skipped so they don't run in eval.
---

# /asserten-skip-tests

Exclude specific generated test cases from future eval runs. The cases stay
in the database (visible, restorable) — they just don't get executed.

Useful when the auto-generated set has cases that don't represent how your
real users behave, or when you've supplied a better version via
`/asserten-add-tests` (in which case `replaces_generated_id` does this
automatically).

## Inputs

- **List:** `/asserten-skip-tests {"test_case_ids": ["id_1", "id_2"]}`
- **Comma-separated:** `/asserten-skip-tests id_1, id_2, id_3`

By default targets v1 (most common). Pass `target=v0|v1|v2a|v2b` to scope.

## What you do

1. Parse the user's input — either a JSON object with `test_case_ids` or a
   comma-separated list of ids.
2. Invoke the CLI:

```bash
echo '{"test_case_ids": ["id_1", "id_2"]}' | python -m client.cli skip-tests
```

3. Show the user how many were skipped + any IDs that weren't found.
4. Reminder: skipped cases are NOT deleted — use `/asserten-unskip-tests`
   to bring them back.
