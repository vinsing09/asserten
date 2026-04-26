# Morning checklist — what to do before friend arrives

Tonight's autonomous build did everything possible without human intervention,
including pushing asserten to https://github.com/vinsing09/asserten (public).
These are the remaining 4 actions:

## 1. Start ngrok tunnel (each time you want friends to hit your laptop)

```bash
# In a new terminal — keep this open while friend is using it
ngrok http 8000
```

Copy the `https://<random>.ngrok.io` URL ngrok prints.

## 2. Set the asserten env in your Claude Code shell

```bash
export ASSERTEN_BACKEND_URL=https://<random>.ngrok.io
# The api key is already set in agentops-backend/.env (overnight build).
# Read it back:
export ASSERTEN_API_KEY=$(grep ASSERTEN_API_KEY ~/Documents/my_projects/agentops-backend/.env | cut -d= -f2)
echo "key: $ASSERTEN_API_KEY"   # share this with friend
```

(Tell your friend the same URL + key when they install.)

## 3. (Backend ASSERTEN_API_KEY is already set + server already running — skip)

The overnight run wrote `ASSERTEN_API_KEY=ak_d47fd5b7c04b08ba15d3dbeb2cad2d4e`
to `agentops-backend/.env` and restarted the server with auth enforced. The
server is at PID `$(cat /tmp/agentops_server.pid)`. If your laptop rebooted,
restart it:

```bash
cd ~/Documents/my_projects/agentops-backend
nohup /opt/anaconda3/bin/python -u main.py > logs/server/main_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > /tmp/agentops_server.pid
```

## 4. Smoke-test before friend arrives

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
