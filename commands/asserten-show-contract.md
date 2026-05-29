---
description: Show the contract for the current agent with mandate-coverage transparency.
---

# /asserten-show-contract

Display the customer's behavioral contract for the agent — total obligations,
forbidden behaviors, tool sequences — plus a transparency table showing
**which mandate categories were covered by the LLM directly vs which were
auto-injected as placeholders**.

## Why this exists

The backend enforces four mandate categories at code level (not just in the
prompt): `GOAL_COMPLETION ≥2`, `REASONING_QUALITY ≥2`, `ESCALATION ≥1`,
`HALLUCINATION_GUARD ≥1`. If the LLM under-delivers on any of those, the
backend injects placeholder obligations marked `auto_injected: true` to
keep coverage honest.

This command makes that visible. If the LLM produced enough coverage on
its own, no placeholders are needed and the table shows clean LLM output.
If the LLM missed a mandate, the table calls out exactly which one and
shows the placeholder text so the customer can decide whether to refine
their system prompt (which would let the LLM produce better natural
coverage on regeneration).

## Inputs

By default targets v1. Pass `target=v0|v1|v2a|v2b` to inspect a specific
version.

- `/asserten-show-contract` — shows v1
- `/asserten-show-contract v0` — shows v0
- `/asserten-show-contract v2a` — shows v2a

## What you do

1. Invoke the CLI:

```bash
echo '{"target": "v1"}' | "${CLAUDE_PLUGIN_ROOT}/bin/asserten-cli" show-contract
```

(or pass just the target as a raw arg: `"${CLAUDE_PLUGIN_ROOT}/bin/asserten-cli" show-contract v1`)

2. Read the table. Each row shows the mandate category, the minimum count
   we require, how many were found in the contract, and how many were
   auto-injected.

3. If `Auto-injected > 0` for any row, that category was thin in the
   LLM's output. The placeholder text gets surfaced below the table.
   Read it; if it doesn't match your domain, refine your system prompt
   to cover that category explicitly and run `/asserten-prepare-eval`
   again — the regenerated contract should land closer to LLM-natural
   coverage.

## What you don't need this for

- Once you've reviewed the contract and approved it, you don't need to
  re-run this on every eval. It's a one-time transparency check after
  contract generation.
