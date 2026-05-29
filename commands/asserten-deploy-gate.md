---
description: Run the deploy gate — block deploys that regress on approved scenarios.
---

# /asserten-deploy-gate

The regression-gate-as-deploy-promise surface. Given a candidate version
and a baseline version, compares the latest eval on each, classifies
every approved test case as:

- `regression`: baseline passed, candidate **failed** (proven) — **blocks deploy**
- `improvement`: baseline failed, candidate passed
- `stable_pass`: both passed
- `stable_fail`: both failed
- `coverage_gap`: case approved but missing from one or both evals (probably added/deleted post-baseline)
- `judge_inconclusive`: judge errored on one side — we can't prove pass or fail

Verdicts:
- **BLOCKED** — at least one proven regression.
- **INCONCLUSIVE** — an eval melted down (judge-error rate over threshold), OR
  (in strict mode) some approved cases couldn't be evaluated. Can't certify;
  re-run `/asserten-eval`.
- **PASSED** — no regressions (and, in strict mode, nothing inconclusive).
- **PASSED_NO_APPROVED** — nothing approved yet; the gate is a no-op.

## Eval prerequisite (auto by default)

If a side has no eval run, the gate **auto-creates one** (`auto_eval=true`,
default) before comparing — so a real eval may run and take a while. Pass
`auto_eval=false` to require pre-existing evals (returns HTTP 400 instead).

## Usage

```bash
echo '{"candidate": "v2b"}' | python -m client.cli deploy-gate
```

- `baseline` is **optional** — omit it (or pass `"auto"`) to compare against the
  previous eval'd version automatically. Pass `{"baseline": "v1"}` to pin it.
- `strict` (default true): inconclusive cases block as INCONCLUSIVE; pass
  `{"strict": false}` to treat them as non-blocking.
- Targets accept aliases `v0|v1|v2a|v2b` or raw version_ids.

## What you do

1. Default: candidate=v2b, baseline=v1 (the most common comparison).
2. Invoke the CLI with the resolved targets.
3. Show the verdict markdown as-is — regression table first if BLOCKED.
4. Follow-up suggestions:
   - **BLOCKED**: surface each regression's failure_origin. If `agent` → suggest re-running optimize-deep, or unapproving the case if it's a false-positive scenario. If `judge` → suggest re-running eval (likely infra noise). If `env` → suggest checking the test stub.
   - **PASSED**: suggest the customer ships, or runs `/asserten-scenarios` to see the full outcome.
   - **PASSED_NO_APPROVED**: suggest `/asserten-approve` on passing scenarios first, then re-running the gate.
