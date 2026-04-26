---
description: DEEP optimize — full cross-refine pipeline on v1 → v2b (~15 min wall, ~$10).
---

# /asserten-optimize-deep

Submits a deep cross-refine job to the backend, polls until done.

## Usage

```bash
echo '{"eval_run_id": "<from-asserten-eval-v1>"}' | python -m client.cli optimize-deep
```

The `eval_run_id` comes from the most recent `/asserten-eval v1`. v0.1 requires the user (or you) to pass it manually.

## What to tell the user

Before running:
> Deep optimize takes 14-20 min wall time and costs ~$10-20 in LLM calls. It runs the full cross-refine pipeline (generate → critique → refine → synthesize → verify with replay-majority) on v1.

While running:
> Polling every 30s. Job will resolve to `completed`, `failed`, or `timeout`.

After:
- If `completed`, run `/asserten-eval v2b` to measure.
- If `failed`, surface the error.
- If `timeout`, the backend job is still running — `/asserten-status` later or check `/improvements/jobs/<job_id>` directly.
