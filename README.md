# asserten

A Claude Code plugin that takes any LLM agent and shows you four versions of it side by side:

- **v0** — what you brought
- **v1** — audited + your selected patches
- **v2a** — LIGHT optimization (free, instant pick-best across K v1 candidates)
- **v2b** — DEEP optimization (~15 min, ~$10-20 of LLM cost — full cross-refine)

…and tells you the pass-rate delta on a fresh test suite for each.

## Status

v0.1 — early. Works for solo demos against a self-hosted backend. Public marketplace listing coming after the API surface stabilizes.

## How it works

```
[your laptop]                     [your backend, hosted]
.claude-plugins/asserten/  ──HTTP──► api.asserten.dev (or ngrok URL)
  - 11 slash commands                 - agentops-backend FastAPI
  - thin Python client                - audit + LIGHT + DEEP optimizers
  - session in ~/.asserten/           - eval pipeline + judges
```

Mode A: the backend handles all LLM calls. You don't share your Anthropic/OpenAI keys with the plugin — the backend operator does.

## Install (developer install for now)

```bash
git clone https://github.com/<USER>/asserten ~/Documents/my_projects/asserten
cd ~/Documents/my_projects/asserten
pip install -e .

# Symlink the plugin into Claude Code's plugin dir:
mkdir -p ~/.claude/plugins
ln -s ~/Documents/my_projects/asserten ~/.claude/plugins/asserten
```

Then restart Claude Code. `/asserten` should autocomplete.

## Configure

```bash
export ASSERTEN_BACKEND_URL=http://localhost:8000   # or ngrok URL, or api.asserten.dev
export ASSERTEN_API_KEY=<your-asserten-key>          # only needed if backend enforces it
```

## First run (10-minute demo)

```
/asserten-ingest examples/sample_agent.json
/asserten-audit
# … review patches; reply "all" or "1,3,5"
/asserten-select all
/asserten-eval v0
/asserten-eval v1
/asserten-optimize-light                # only if you have K candidate v1s — see notes
/asserten-eval v2a
/asserten-optimize-deep <eval_run_id>   # ~15 min, ~$10-20
/asserten-eval v2b
/asserten-compare
```

Or run the whole flow with one command:

```
/asserten-run examples/sample_agent.json
```

## Slash command reference

| command | what it does |
|---|---|
| `/asserten` | Help / overview |
| `/asserten-status` | Show current session state |
| `/asserten-reset` | Clear the session |
| `/asserten-ingest <path>` | Upload an agent → draft |
| `/asserten-audit` | Get suggested patches (always shows all + asks which to keep) |
| `/asserten-select <answer>` | Apply selected patches → v0 + v1 |
| `/asserten-eval <v0\|v1\|v2a\|v2b>` | Run full eval on a version |
| `/asserten-failures` | _v0.1_: redirects to status — full failures endpoint pending |
| `/asserten-optimize-light` | LIGHT (1A pick-best, 0 LLM cost) → v2a |
| `/asserten-optimize-deep <eval_run_id>` | DEEP (cross-refine, slow) → v2b |
| `/asserten-compare` | 4-way pass-rate table |
| `/asserten-run <path>` | Mega-orchestration of all steps above |

## What this gives you

**Concrete: a 4-way pass-rate comparison table with deltas vs your raw v0.** Useful for:
- Auditing whether your agent's prompt actually hurts vs helps on edge cases
- Choosing between cheap (LIGHT) vs expensive (DEEP) optimization based on real numbers
- Identifying which test cases each version flips on (failures endpoint coming in v0.2)

## Limits in v0.1

- **Failures view is a stub** — relies on the eval summary's `failed/total` count rather than per-case detail. The `eval_results` endpoint is on the backend roadmap.
- **LIGHT requires K pre-existing candidate v1s.** v0.1 doesn't auto-bulk-audit — you either reuse an existing audit study or populate `candidate_v1_ids` manually in `~/.asserten/session.json`. v0.2 ships `/asserten-audit-bulk K=10` to fix this.
- **DEEP optimize requires you to pass `eval_run_id` from the prior `/asserten-eval v1` output.** v0.2 will auto-resolve this.
- **Single-active-session model.** Run on one agent at a time. Use `/asserten-reset` to switch.

## Development

```bash
pip install -e ".[test]"
pytest -v                                       # 60 unit tests, ~1.5s
ASSERTEN_E2E_BACKEND_URL=http://localhost:8000 \
  ASSERTEN_E2E_AGENT_ID=<id> \
  ASSERTEN_E2E_VERSION_ID=<vid> \
  pytest tests/test_e2e_smoke.py -v             # 4 E2E tests against real backend
```

`PROJECT_KNOWLEDGE.md` has architecture decisions, layout, and chronological history.

## License

MIT.
