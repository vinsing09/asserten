---
description: Run the deploy gate — block deploys that regress on approved scenarios.
---

# /asserten-deploy-gate

The regression-gate-as-deploy-promise surface. Given a candidate version
and a baseline version, compares the latest eval on each, classifies
every approved test case as:

- `regression`: baseline passed, candidate failed (or judge_errored on a previously-passing case) — **blocks deploy**
- `improvement`: baseline failed, candidate passed
- `stable_pass`: both passed
- `stable_fail`: both failed
- `coverage_gap`: case approved but missing from one or both evals (probably added/deleted post-baseline)

Verdict is **BLOCKED** if any regression exists, **PASSED** otherwise.
A third verdict **PASSED_NO_APPROVED** signals the gate is a no-op
because nothing has been approved yet — the customer should run
`/asserten-approve` on their critical scenarios before relying on the
gate for deploy decisions.

## v0.1 prerequisite

Both candidate and baseline must already have eval runs. If either
hasn't been eval'd, the gate returns HTTP 400 with a "run
/asserten-eval first" message. (Future versions may auto-trigger eval;
v0.1 is explicit.)

## Usage

```bash
echo '{"candidate": "v2b", "baseline": "v1"}' | python -m client.cli deploy-gate
```

Targets accept aliases `v0|v1|v2a|v2b` or raw version_ids.

## What you do

1. Default: candidate=v2b, baseline=v1 (the most common comparison).
2. Invoke the CLI with the resolved targets.
3. Show the verdict markdown as-is — regression table first if BLOCKED.
4. Follow-up suggestions:
   - **BLOCKED**: surface each regression's failure_origin. If `agent` → suggest re-running optimize-deep, or unapproving the case if it's a false-positive scenario. If `judge` → suggest re-running eval (likely infra noise). If `env` → suggest checking the test stub.
   - **PASSED**: suggest the customer ships, or runs `/asserten-scenarios` to see the full outcome.
   - **PASSED_NO_APPROVED**: suggest `/asserten-approve` on passing scenarios first, then re-running the gate.
