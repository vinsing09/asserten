# asserten — project knowledge

**One-line:** Asserten is a Claude Code plugin that walks a user through the agentops-backend pipeline (contract → tests → audit → patch select → eval → LIGHT/DEEP optimize → compare) one slash command at a time.

## Session protocol (mandatory)

**Read this file at the top of every session.** Then read the most recent `docs/sessions/<date>.md` if any. Anything that changed materially (new command, new client field, broken endpoint, friend feedback) gets appended here under "Chronological progress" before close.

## Objective

Ship a plugin so an external user can:
1. Bring an agent (raw system prompt + tool schemas + business goal)
2. Generate contract + test cases against it
3. Get audit suggestions, **manually pick which patches** to keep → v1
4. Eval v0 (raw) and v1
5. Inspect failure cases on v1
6. Run **LIGHT** optimization (1A pick-best across K v1 candidates) → v2a
7. Run **DEEP** optimization (cross-refine on v1) → v2b
8. See a 4-way comparison table: v0 / v1 / v2a / v2b

LLM costs are paid by the backend operator (Mode A in the original brainstorm). Users only need an asserten API key.

## Architecture

```
[user laptop]                       [backend, hosted]
.claude-plugins/asserten/  ──HTTP──► api.asserten.dev (or ngrok URL)
  - 11 slash commands                 - agentops-backend FastAPI
  - thin Python client                - LIGHT optimizer (1A pick-best)
  - session state in ~/.asserten/     - DEEP optimizer (cross-refine)
                                      - eval pipeline + judges
```

**Key file boundary:** `client/` is pure Python HTTP, no Claude Code dependencies. A future TypeScript frontend can hand-port or codegen from the OpenAPI spec.

## Repo layout

```
asserten/
├── README.md                       # install + ngrok + first run
├── PROJECT_KNOWLEDGE.md            # this file
├── .claude-plugin/
│   ├── plugin.json
│   └── commands/<name>.md          # 11 slash commands (Decision 1B)
├── client/                         # pure Python, frontend-reusable
│   ├── api.py                      # HTTP wrapper (≤200 lines)
│   ├── session.py                  # cross-command state
│   ├── models.py                   # dataclasses
│   └── format.py                   # render helpers
├── tests/
│   ├── test_api.py
│   ├── test_session.py
│   ├── test_format.py
│   └── test_e2e_smoke.py           # against real backend
├── examples/
│   └── sample_agent.json
└── pyproject.toml
```

## Decisions locked

- **Decision 1B (step-by-step + mega):** ship 10 step commands + 1 `/asserten-run` mega-orchestrator.
- **Decision 2B (patch selection always lists all):** every audit output ends with a numbered patch list and asks the user "which to keep? (e.g. `1,3,5` or `all`)".
- **Mode A backend pays LLM costs:** users send agent through the user's backend; backend handles judges + LLM calls.
- **Single-secret auth:** `X-Asserten-Key: <ASSERTEN_API_KEY>` header on every mutating request.
- **Session state:** `~/.asserten/session.json` keyed by `(backend_url, agent_id)`. Each command reads + appends fields. Cleared with `/asserten-reset`.
- **Module size cap:** every Python file ≤200 lines. Slash command markdown files ≤100 lines.

## Chronological progress

### 2026-04-26 — initial scaffold
- Created repo at `~/Documents/my_projects/asserten/`. Sibling to `agentops-backend/`.
- pyproject.toml: deps `httpx`, `pydantic`. Test deps `pytest`, `respx`.
- `.claude-plugin/plugin.json` v0.1.0 manifest.
- `.gitignore` covers `__pycache__/`, `.asserten/`, `asserten-session.json`, `.env`.

## Open questions / things deliberately deferred

- **K candidates for LIGHT optimization:** v0.1 plugin assumes the user has already run `/asserten-audit` multiple times to populate K candidate v1s. Future: an `/asserten-audit-bulk K=10` command that does this in one call.
- **TypeScript frontend:** `client/models.py` should stay flat dataclasses so `pydantic.to_json` ports cleanly. Don't add inheritance or polymorphism without thinking about FE codegen first.
- **MCP server vs slash commands:** v0.1 is slash commands only. MCP server is a future add for tool-based access from other agents.
- **Error reporting back to backend:** if a slash command crashes, the user sees the traceback. No automatic crash report. Add later.

## How to update this document

After every session that changes architecture, decisions, or open items, append to "Chronological progress" with a dated entry. Don't rewrite history — preserve the timeline.
