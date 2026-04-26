---
description: LIGHT optimize — pick top-1 v1 from K candidates by pass_rate (zero LLM cost).
---

# /asserten-optimize-light

Picks the best v1 candidate by pass_rate and records it as v2a.

```bash
python -m client.cli optimize-light
```

## v0.1 prerequisite

The session must have `candidate_v1_ids` populated. v0.1 doesn't auto-generate K candidates — that requires the future `/asserten-audit-bulk` command. Workarounds for tomorrow's demo:

1. Use an agent that already has audit-study artifacts (e.g. existing `bea9a565` / `f1acb8ab` from prior sweeps in the backend DB).
2. Manually populate `candidate_v1_ids` in `~/.asserten/session.json` before running this command.

If the command says "no candidate v1 ids", tell the user about (1) and (2).

## What this returns

A chosen v2a version_id, its pass_rate, the delta vs median, latency (~0.01s), and `0` LLM calls. The chosen version is recorded as v2a in session — run `/asserten-eval v2a` to confirm.
