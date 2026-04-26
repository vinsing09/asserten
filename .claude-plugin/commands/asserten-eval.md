---
description: Run the full eval suite on a specific version (v0, v1, v2a, or v2b).
---

# /asserten-eval

Eval one of the four agent versions and record the pass_rate in session.

## Usage

- `/asserten-eval v0` — eval the raw agent
- `/asserten-eval v1` — eval after audit + selected patches
- `/asserten-eval v2a` — eval after LIGHT optimize
- `/asserten-eval v2b` — eval after DEEP optimize

## What you do

```bash
echo '{"target": "<v0|v1|v2a|v2b>"}' | python -m client.cli eval
```

The eval runs synchronously. It can take ~30s-3min depending on test case count and judge load. Tell the user "evaluating, this can take up to 3 minutes" before running, then show the result.

## Notes
- If the target version doesn't exist yet, the command will say so.
- An eval can come back `INVALID` if the judge_error_rate exceeded 10% — relay that to the user; they can re-run.
