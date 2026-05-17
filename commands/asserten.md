---
description: Asserten plugin help — drive an agent through the agentops-backend pipeline.
---

# /asserten — overview

Asserten walks an agent through 4 versions you can compare:

- **v0** = raw agent prompt (what the user brought)
- **v1** = audit + user-selected patches
- **v2a** = LIGHT optimization (1A pick-best across K v1 candidates)
- **v2b** = DEEP optimization (cross-refine on v1)

## Step-by-step commands

| step | command | what it does |
|---|---|---|
| 1 | `/asserten-ingest` | upload agent prompt + tool schemas → creates a draft |
| 2 | `/asserten-audit` | run audit, show suggested patches |
| 3 | `/asserten-select all` | accept patches → creates v0 + v1 |
| 4 | `/asserten-eval v0` | eval v0 |
| 5 | `/asserten-eval v1` | eval v1 |
| 6 | `/asserten-optimize-light` | LIGHT optimize → v2a |
| 7 | `/asserten-eval v2a` | eval v2a |
| 8 | `/asserten-optimize-deep` | DEEP optimize → v2b (slow ~15min) |
| 9 | `/asserten-eval v2b` | eval v2b |
| 10 | `/asserten-compare` | 4-way pass-rate table |

Or run the whole flow with `/asserten-run`.

Helpers: `/asserten-status` (current session), `/asserten-reset` (clear).

## Bring your own test cases (optional, any time after step 3)

| command | what it does |
|---|---|
| **`/asserten-byoe`** | **plain-English entry: type `input` + what agent should say/call/not do; we fill in the schema** |
| `/asserten-add-tests path/to/tests.json` | full-schema JSON upload (for technical users) |
| `/asserten-skip-tests id_1, id_2` | mark generated cases as skipped (excluded from eval) |
| `/asserten-unskip-tests id_1` | re-include previously-skipped cases |

These cases run together with the generated set and drive patches just like
generated cases. Useful when you already know the failure modes you care
about — supply them directly instead of relying on the generator to find
them.

**Prefer `/asserten-byoe` if you're not a developer.** It walks you through
prompts ("what does the user say?" → "what should the agent reply with?")
and handles the schema for you. Use `/asserten-add-tests` only if you've
already written the full structured JSON.

## Transparency / "why did this version land where it did?"

| command | what it does |
|---|---|
| `/asserten-show-contract` | show the contract with mandate-coverage breakdown (which categories the LLM produced directly vs which were auto-injected as placeholders) |

Use after `/asserten-prepare-eval` or `/asserten-select`. If you see
auto-injected obligations, your system prompt under-covered that mandate
category — refine the prompt and regenerate for cleaner LLM-natural
coverage.

## Setup

Before any command, set:
```bash
export ASSERTEN_BACKEND_URL=https://your-backend-url
export ASSERTEN_API_KEY=<your-key>
```

(Or pass them on `/asserten-ingest` — see that command's help.)
