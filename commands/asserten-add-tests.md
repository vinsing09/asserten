---
description: Upload customer-supplied test cases alongside the auto-generated ones.
---

# /asserten-add-tests

Add your own test cases to the current agent. They run alongside the
auto-generated set and drive patches just like generated cases.

This is the BYOE (Bring Your Own Examples) entry point — useful when you
already know specific failure modes you want the optimization to address.

## Inputs

Two ways to supply the cases:

- **File path:** `/asserten-add-tests path/to/my-tests.json`
- **Inline JSON:** paste the JSON in your message; the slash command parses it.

## Expected JSON shape

A JSON file or object with either a top-level array OR a `test_cases` key:

```json
{
  "test_cases": [
    {
      "scenario": "user asks for refund on out-of-policy item",
      "input_text": "I want a refund for the headphones I bought 60 days ago.",
      "tool_stubs": {
        "lookup_order": {
          "response": {"order_id": "ord_1", "purchased_at": "2026-03-01"},
          "latency_ms": 100,
          "simulate_failure": false
        }
      },
      "assertions": [
        {"id": "a_1", "type": "output_contains", "value": "policy", "required": true}
      ],
      "obligation_ids": [],
      "tags": ["edge_case"],
      "replaces_generated_id": null
    }
  ]
}
```

Field rules (server-side validation):

- `assertions[].type` must be one of: `tool_called`, `tool_not_called`,
  `param_contains`, `output_contains`, `max_latency_ms`, `tool_sequence`.
- `tags` must come from: `happy_path`, `tool_failure`, `no_tool_needed`,
  `edge_case`, `wrong_params`, `multi_tool`.
- `tool_stubs` keys must match the agent's actual tool names.
- `replaces_generated_id` (optional) — if set, must reference an existing
  generated case; that case is auto-marked skipped.

Bad cases are reported per-case in `errors[]`; good cases still insert.

## Target version

Cases attach to v1 by default. Pass `target=v0|v1|v2a|v2b` to attach to a
specific version — e.g. when iterating on v2a after optimize.

## What you do

1. Parse the user's input (file path or inline JSON).
2. If essential fields look missing, ask the user to fix the JSON.
3. Invoke the CLI:

```bash
echo '{"file": "<path>"}' | python -m client.cli add-tests
```

or with inline cases + target:

```bash
echo '{"test_cases": [...], "target": "v1"}' | python -m client.cli add-tests
```

4. Show the user the inserted count + IDs + any per-case errors / warnings.
   If unknown obligation_ids appeared, surface them as warnings (non-fatal).
5. Tell them to run `/asserten-eval v1` (or whichever target) to see the
   pass-rate including their cases.
