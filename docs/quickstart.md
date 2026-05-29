# Asserten

**Make your AI agent measurably more reliable — and prove it.**

*A Claude Code plugin. About 10 minutes to your first result.*

---

## The problem

You ship an AI agent. It demos well. Then in production it quietly does the
wrong thing — refunds an order it shouldn't, loops on a tool call, fumbles an
edge case — and you hear about it from a customer, not a test.

"We tested it" is usually thin. A handful of test cases makes almost any agent
look good. In our own runs, one agent scored **93% on a 15-case test and 58%
when we ran 75 cases** — same agent, same prompt. The small test was lying.

## What asserten does

Hand it your agent (its instructions + the tools it can call). Asserten:

1. **Audits** the prompt and suggests concrete fixes.
2. **Generates a real test suite** — dozens of scenarios across happy paths,
   tool failures, wrong inputs, and edge cases (not the three you'd think of).
3. **Scores four versions side by side**, each with its pass-rate on that suite:

   | version | what it is |
   |---|---|
   | **v0** | the agent you brought |
   | **v1** | v0 + the audit fixes you accepted |
   | **v2a / v2b** | lightly / deeply optimized variants |

4. **Gates your deploys.** Approve the scenarios you care about; asserten blocks
   any new version that regresses on them.

You walk away with one honest number per version — *did this change help or
hurt?* — and a gate that stops silent regressions before they ship.

## See it in ~10 minutes

You need Claude Code, plus a **backend URL and key** (ask whoever shared this).

**1. Install** (in Claude Code):

```
/plugin marketplace add vinsing09/asserten
/plugin install asserten@asserten
```

**2. Point it at the backend** (in your terminal):

```
export ASSERTEN_BACKEND_URL=<the URL you were given>
export ASSERTEN_API_KEY=<the key you were given>
```

**3. Run the flow** on the bundled sample agent:

```
/asserten-ingest examples/sample_agent.json
/asserten-audit
/asserten-select all
/asserten-prepare-eval
/asserten-eval v0
/asserten-eval v1
/asserten-compare
```

## What you'll see

A side-by-side comparison with the delta vs your original:

```
version   pass-rate
v0        62%
v1        84%   (+22)
```

And if you approve scenarios and run the deploy gate on a new version:

```
🛑 BLOCKED — 1 approved scenario regressed:
   "Refund within policy"   passed → failed
```

That's the whole point: you see exactly what got better, what got worse, and
nothing ships that breaks a scenario you signed off on.

## Try your own agent

Swap the sample for yours — a small JSON file:

```json
{
  "name": "My Agent",
  "raw_system_prompt": "You are ...",
  "tool_schemas": [{"name": "...", "description": "...", "parameters": { }}],
  "business_goal": "One line on what success means for this agent."
}
```

Then `/asserten-ingest path/to/your_agent.json` and run the same flow. Prefer
plain English? `/asserten-byoe` lets you type "the user says X, the agent should
do Y" and fills in the rest.

## Good to know

- **Your key is capped** (3 agents) so you can't run up a surprise bill, and your
  token usage is tracked transparently.
- **You never share your own LLM keys** — the backend holds those.
- **Open source** (MIT): [github.com/vinsing09/asserten](https://github.com/vinsing09/asserten)

Stuck? A connection error almost always means `ASSERTEN_BACKEND_URL` is wrong
or unreachable; a 401 means the key is not set.
