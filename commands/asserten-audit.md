---
description: Run the audit pass on the current draft → numbered list of suggested patches.
---

# /asserten-audit

Calls the backend audit endpoint and shows suggested patches.

```bash
python -m client.cli audit
```

The output ends with a prompt asking the user which patches to keep. **After the user answers, immediately invoke `/asserten-select <answer>`** — don't wait for them to type the slash command themselves.

## Notes
- If the user has not run `/asserten-ingest` yet, the command will tell them; just relay that.
- This step does NOT create a v1 — the user must `/asserten-select` to commit.
