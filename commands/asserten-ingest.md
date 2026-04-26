---
description: Upload an agent (raw system prompt + tool schemas + business goal) → asserten draft.
---

# /asserten-ingest

Take the user's agent definition and submit it as a draft. The user can either:

- pass a JSON file path: `/asserten-ingest path/to/agent.json`
- paste the agent inline (you'll have to gather: name, raw_system_prompt, tool_schemas, business_goal, desired_behaviors)

## Expected JSON shape

```json
{
  "name": "Customer Support Agent",
  "raw_system_prompt": "You are a polite assistant who helps customers with returns...",
  "tool_schemas": [{"name": "lookup_order", "parameters": {...}}],
  "business_goal": "Resolve customer support tickets accurately within 3 turns.",
  "desired_behaviors": ["always confirm refund amount before processing", "escalate angry users"]
}
```

## What you do

1. If a file path was provided, read it. If the user pasted JSON inline, parse it.
2. If essential fields (`name`, `raw_system_prompt`) are missing, ask the user to provide them.
3. Call the asserten CLI with the parsed JSON:

```bash
echo '<the-json-as-one-line>' | python -m client.cli ingest
```

4. Show the user the resulting `draft_id` and tell them to run `/asserten-audit` next.
