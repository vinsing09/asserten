---
description: Mega-orchestration — drive the entire asserten flow with one command, pausing at patch selection.
---

# /asserten-run

End-to-end orchestrated flow. Use this for demos. The slash command sequence executes:

```
/asserten-ingest <agent.json>
/asserten-audit                       ← pause here for user to pick patches
/asserten-select <user-answer>
/asserten-eval v0
/asserten-eval v1                     ← capture eval_run_id
/asserten-optimize-light              ← only if candidate_v1_ids exist
/asserten-eval v2a                    ← only if v2a was created
/asserten-optimize-deep <eval_run_id> ← warn user this takes ~15min
/asserten-eval v2b
/asserten-compare
```

## Usage

```
/asserten-run path/to/agent.json
```

## What you do as the agent

1. Parse the file path or inline JSON the user passed.
2. Call `/asserten-ingest` with the agent shape.
3. Call `/asserten-audit`. **STOP** at the patch-selection prompt — do NOT auto-pick.
4. After the user replies (`all`, `1,3,5`, `none`), call `/asserten-select <answer>`.
5. Call `/asserten-eval v0`, then `/asserten-eval v1`. Capture the `eval_run_id` from v1's output (you'll need it for deep optimize).
6. Call `/asserten-optimize-light`. If it errors with "no candidate v1 ids", skip v2a steps and tell the user "v2a unavailable — needs `/asserten-audit-bulk` (future feature)".
7. If v2a was produced, `/asserten-eval v2a`.
8. **Confirm with the user** before running deep optimize (it costs ~$10-20 and takes ~15 min). Surface "this is the slow expensive step — proceed?". If yes, call `/asserten-optimize-deep <eval_run_id>` and let it block.
9. After deep completes, `/asserten-eval v2b`.
10. Finally call `/asserten-compare` and show the 4-way table.

## Failure handling

If any step errors, surface the error and stop. The session retains state, so the user can resume by calling individual commands.
