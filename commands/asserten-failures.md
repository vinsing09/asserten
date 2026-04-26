---
description: Show failing test cases for the most recent v1 eval (or specified version).
---

# /asserten-failures

v0.1 limitation: this command currently surfaces what the eval summary already reports. A dedicated `/eval-results/{run_id}/failures` endpoint is on the backend roadmap.

For now, run:

```bash
python -m client.cli status
```

And tell the user: "Detailed per-case failures aren't exposed via the API in v0.1. The eval summary tells you `failed/total`. To dig in, query the backend's `eval_results` table directly via SQL or the next plugin release will surface failures inline."
