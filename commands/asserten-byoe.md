---
description: Add your own test cases in plain English (input → expected output).
---

# /asserten-byoe

Add test cases by describing **what you want to happen** in plain English,
not by writing JSON schemas. Each test case is one input plus expectations
about what the agent should say, should call, or should not do.

This is the BYOE (Bring Your Own Examples) entry point. Test cases added
here run alongside the auto-generated ones in eval — they drive patches
just like generated cases do.

## Three ways to add cases

### 1. Interactive (best for one-off cases)

Just type `/asserten-byoe` with nothing else.

You'll be walked through these prompts one at a time:

1. **"What does the user say?"** → the input message.
2. **"What should the agent's reply contain?"** → comma-separated phrases.
3. **"What tools should the agent call (if any)?"** → comma-separated tool names.
4. **"Anything the agent should NOT do?"** → free text.
5. **"Add another case, or save?"** → loop or finish.

When you say save, the JSON is built and submitted in one call.

### 2. Inline JSON (best for 2-5 cases)

Paste the JSON directly:

```
/asserten-byoe {"test_cases": [
  {
    "input": "I want a refund for order #123",
    "agent_should_say": ["order ID", "return policy"],
    "agent_should_call": ["lookup_order"],
    "agent_should_not": ["approve refund without verification"]
  }
]}
```

### 3. File upload (best for >5 cases)

```
/asserten-byoe path/to/byoe.json
```

File can be a JSON array OR an object with `test_cases: [...]`.

## The simple shape

Every BYOE test case looks like:

```json
{
  "input": "what the user says (required)",
  "agent_should_say": ["phrase1", "phrase2"],
  "agent_should_call": ["tool_name1"],
  "agent_should_not": ["thing in plain English"]
}
```

- `input` is **required**.
- All three expectation lists are **optional**. Use any combination.
- `agent_should_call` tool names must match the agent's actual tools — the
  server rejects unknown tools per-case with a clear error.
- `agent_should_not` is preserved in the test case description; semantic
  judges enforce it at eval time (hallucination_guard, reasoning_quality).

## What happens server-side

For each case, the backend:

1. Validates the shape and tool names.
2. Calls an LLM (~$0.001/case) to pick a scenario label, suggest a realistic
   tool stub response for any tool in `agent_should_call`, and pick a tag.
3. Builds the structured test case and inserts it as `source = "user_provided"`.

If the LLM call fails (timeout, auth, etc.), the backend falls back to a
deterministic minimal test case so your input is never lost. The CLI
output flags any fallbacks so you can re-run those cases later.

## What you do (as the assistant running this command)

### If user typed just `/asserten-byoe` (no args):

Start the interactive walk-through:

1. Ask: "**What does the user say to the agent?**"
2. Once they answer, ask: "**What should the agent say back? (Comma-separated phrases, or 'none')**"
3. Then: "**What tools should the agent call? (Comma-separated names, or 'none')**"
4. Then: "**Anything the agent should NOT do? (Free text, or 'none')**"
5. Build a JSON object from these answers.
6. Ask: "**Add another case, or save and submit?**"
7. Loop or submit.

When ready to submit, run:

```bash
echo '{"test_cases": [<all-the-cases>]}' | python -m client.cli byoe
```

### If user passed a file path:

```bash
echo '{"file": "<path>"}' | python -m client.cli byoe
```

### If user pasted inline JSON:

```bash
echo '<their-json>' | python -m client.cli byoe
```

### After the CLI returns:

- Show the inserted IDs + scenarios summary.
- Surface any per-case errors prominently (don't bury them).
- If any case used the deterministic fallback (LLM enrichment failed),
  call it out — those cases work but the scenario name + tool_stubs are
  less polished and the user may want to re-add them later.
- Tell the user to run `/asserten-eval v1` to see the pass rate including
  the BYOE cases.

## Target version

Cases attach to v1 by default. Pass `target=v0|v1|v2a|v2b` in the JSON
body to attach to a different version.
