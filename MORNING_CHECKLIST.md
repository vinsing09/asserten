# Morning checklist — what to do before friend arrives

Tonight's autonomous build wrote everything else. These are the 5 actions that need a human (you):

## 1. Create the public GitHub repo (once, ~30s)

```bash
cd ~/Documents/my_projects/asserten
gh repo create asserten --public --source . --remote origin --push
```

Or via the web: https://github.com/new → name `asserten`, public, then:
```bash
cd ~/Documents/my_projects/asserten
git remote add origin git@github.com:<YOUR-USERNAME>/asserten.git
git add .
git commit -m "initial: asserten v0.1 plugin scaffold"
git push -u origin main
```

## 2. Start ngrok tunnel (each time you want friends to hit your laptop)

```bash
# In a new terminal — keep this open while friend is using it
ngrok http 8000
```

Copy the `https://<random>.ngrok.io` URL ngrok prints.

## 3. Set the asserten env in your Claude Code shell

```bash
export ASSERTEN_BACKEND_URL=https://<random>.ngrok.io
export ASSERTEN_API_KEY=<pick-a-shared-secret>
```

(Tell your friend the same URL + key when they install.)

## 4. Set the same secret on the backend

```bash
cd ~/Documents/my_projects/agentops-backend
# Append (don't overwrite) the .env so the existing keys stay:
echo "ASSERTEN_API_KEY=<same-secret-as-step-3>" >> .env
# Restart the backend so it picks up the new env:
kill $(cat /tmp/agentops_server.pid)
nohup /opt/anaconda3/bin/python -u main.py > logs/server/main_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > /tmp/agentops_server.pid
```

## 5. Smoke-test before friend arrives

```bash
# In Claude Code:
/asserten-status            # should say "No active session"
/asserten-ingest ~/Documents/my_projects/asserten/examples/sample_agent.json
/asserten-audit             # should return numbered patches
/asserten-select 1,2        # accept first two
/asserten-eval v0           # should return a pass_rate
```

If any of those fail, check `logs/server/main_*.log` for backend errors.

## What's already done (autonomously, overnight)

- Backend: LIGHT optimize HTTP endpoint shipped, X-Asserten-Key auth wired in, both pushed to master.
- Asserten repo scaffolded at `~/Documents/my_projects/asserten/` with:
  - 4 client modules (`api.py`, `session.py`, `models.py`, `format.py`) + 1 CLI dispatcher.
  - 11 slash command markdown files in `.claude-plugin/commands/`.
  - 60 unit tests passing (4 E2E tests pass when backend is running).
  - This checklist + README + a sample agent.
- Both repos still need to be made private/public per your plan: `agentops-backend` private, `asserten` public.

## Stretch (only if you have extra time)

- Move backend from ngrok to Fly.io for a stable URL: `cd ~/Documents/my_projects/agentops-backend && fly launch`. Plan ~30 min.
- Make `agentops-backend` repo private: GitHub Settings → Danger Zone → Change visibility.

## When friend leaves

Append a line to `asserten/PROJECT_KNOWLEDGE.md` under "Chronological progress" with what worked, what didn't, what surprised them. That's how the plugin gets better.
