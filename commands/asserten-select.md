---
description: Accept a subset of audit patches → creates v0 (raw) + v1 (audit + accepted patches).
---

# /asserten-select

The user's answer to the audit prompt. Forms accepted:

- `/asserten-select all` → keep every suggested patch
- `/asserten-select 1,3,5` → keep patches 1, 3, and 5
- `/asserten-select none` → keep nothing (v1 = v0)

## What you do

Pass the answer into the asserten CLI:

```bash
echo '{"answer": "<user-answer>"}' | python -m client.cli select
```

After this completes successfully, the user has a v0 and v1 in the session.

Tell them:
- The number of patches accepted
- Suggested next step: `/asserten-eval v0` (or `/asserten-eval v1` to skip ahead)
