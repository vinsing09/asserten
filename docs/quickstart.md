# Asserten — Quickstart

*A Claude Code plugin for making LLM agents measurably more reliable.*

Asserten takes any agent (its system prompt + tool definitions), audits it,
generates a behavioral test suite, and shows you four versions side by side with
the pass-rate on a fresh suite for each — then lets you gate deploys on the
scenarios you care about.

| version | what it is |
|---|---|
| **v0** | the prompt you brought, untouched |
| **v1** | v0 + the audit fixes you accepted |
| **v2a** | LIGHT optimization — pick-best across candidates (free, instant) |
| **v2b** | DEEP optimization — full cross-refine (~15 min) |

---

## Before you start: you need a backend

Asserten is a **thin client**. The audit, test generation, evaluation, and
optimization all run in a separate **backend service** that holds the LLM API
keys. The plugin just drives it over HTTP — so you never hand your
Anthropic/OpenAI keys to the plugin.

**You need a backend URL and (if it's enforced) an API key before anything will
run.** Ask whoever shared this with you for both.

---

## 1. Install (in Claude Code)

**Marketplace (recommended):**

```
/plugin marketplace add vinsing09/asserten
/plugin install asserten@asserten
```

**Or developer install:**

```bash
git clone https://github.com/vinsing09/asserten ~/asserten
cd ~/asserten && pip install -e .
mkdir -p ~/.claude/plugins && ln -s "$PWD" ~/.claude/plugins/asserten
```

Restart Claude Code, then type `/asserten` — the commands should autocomplete.

## 2. Configure the backend

In the terminal where you launch Claude Code:

```bash
export ASSERTEN_BACKEND_URL=https://<your-backend-host>   # default http://localhost:8000
export ASSERTEN_API_KEY=<your-key>                        # if the backend enforces auth
```

If commands fail with a connection error, this is almost always the cause —
the URL is unreachable or the key is missing.

## 3. Run the 10-minute flow

A sample agent (`examples/sample_agent.json`) ships with the plugin.

```
/asserten-ingest examples/sample_agent.json   # hand over the agent → draft
/asserten-audit                                # see suggested prompt fixes
/asserten-select all                           # accept them → creates v0 + v1
/asserten-prepare-eval                          # generate the contract + test cases
/asserten-eval v0                               # eval the raw agent
/asserten-eval v1                               # eval the audited agent
/asserten-compare                               # v0 vs v1 pass-rate table
```

That already answers "did the audit actually help?" To go further:

```
/asserten-optimize-deep <eval_run_id>           # optimize v1 → v2b  (~15 min)
/asserten-eval v2b
/asserten-scenarios v1                          # ✓/✗ dashboard per scenario
/asserten-approve all-passing                   # lock in the passing scenarios
/asserten-deploy-gate {"candidate": "v2b"}      # block a deploy that regresses on them
```

> **Tip:** the test-set size defaults to 40. Override it on
> `/asserten-prepare-eval {"count": 60}` — 15 is too small (it inflates the
> pass rate), and very large counts hit a redundancy ceiling.

## Command cheat sheet

**Setup** — `/asserten` (help) · `/asserten-ingest <path>` · `/asserten-status` · `/asserten-reset`

**Contract & tests** — `/asserten-audit` · `/asserten-select all|1,3,5|none` ·
`/asserten-prepare-eval` · `/asserten-show-contract`

**Your own test cases** — `/asserten-byoe` (plain English) ·
`/asserten-add-tests <path>` · `/asserten-skip-tests <ids>` · `/asserten-unskip-tests <ids>`

**Evaluate & optimize** — `/asserten-eval <v0|v1|v2a|v2b>` · `/asserten-failures` ·
`/asserten-optimize-light` · `/asserten-optimize-deep <eval_run_id>` · `/asserten-compare`

**Outcomes & deploy gate** — `/asserten-scenarios <version>` ·
`/asserten-approve <ids|all-passing>` · `/asserten-unapprove <ids>` ·
`/asserten-deploy-gate {"candidate":"v2b"}`

**One-shot** — `/asserten-run <path>` (drives the whole flow, pausing at patch selection)

## Bring your own agent

Instead of the sample, ingest your own. The shape is:

```json
{
  "name": "My Agent",
  "raw_system_prompt": "You are ...",
  "tool_schemas": [{"name": "...", "description": "...", "parameters": { }}],
  "business_goal": "One line on what success means for this agent."
}
```

Save it as a `.json` file and `/asserten-ingest path/to/your_agent.json`.

## Troubleshooting

| symptom | fix |
|---|---|
| commands don't autocomplete | restart Claude Code; confirm the plugin installed |
| connection / timeout error | check `ASSERTEN_BACKEND_URL` is reachable |
| `401` / key error | set `ASSERTEN_API_KEY` to the key you were given |
| "no v1 yet" | run `/asserten-select` before `/asserten-prepare-eval` |
| eval says "generate contract first" | run `/asserten-prepare-eval` before `/asserten-eval` |

---

Asserten is MIT-licensed and open: https://github.com/vinsing09/asserten
