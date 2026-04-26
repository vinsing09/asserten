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

## Setup

Before any command, set:
```bash
export ASSERTEN_BACKEND_URL=https://your-backend-url
export ASSERTEN_API_KEY=<your-key>
```

(Or pass them on `/asserten-ingest` — see that command's help.)
