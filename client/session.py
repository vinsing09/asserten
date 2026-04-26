"""Cross-command session state for asserten.

Slash commands are independent processes — they need a place to remember
what `/asserten-ingest` produced (`agent_id`) so `/asserten-contract` can
reference it without the user re-typing.

State lives at `~/.asserten/session.json` (overrideable via env
`ASSERTEN_SESSION_PATH`). Single-active-session model: simpler than
per-agent, fits the "one demo at a time" use case for v0.1.

Use `Session.update(field=value)` for atomic writes — never hand-edit the
JSON during a multi-step flow.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from client.models import SessionState


def session_path() -> Path:
    override = os.getenv("ASSERTEN_SESSION_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".asserten" / "session.json"


def load_session(backend_url: str | None = None,
                 api_key: str | None = None) -> SessionState:
    """Load existing session OR start a fresh one.

    If a fresh session is implied (no file yet), backend_url is required.
    api_key falls back to env ASSERTEN_API_KEY if not provided.
    """
    path = session_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            state = SessionState.from_dict(data)
            # Allow caller to override backend_url + api_key on load.
            if backend_url:
                state.backend_url = backend_url
            if api_key:
                state.api_key = api_key
            return state
        except (json.JSONDecodeError, KeyError):
            pass  # fall through to fresh init

    if not backend_url:
        backend_url = os.getenv("ASSERTEN_BACKEND_URL", "http://localhost:8000")
    if api_key is None:
        api_key = os.getenv("ASSERTEN_API_KEY", "")
    return SessionState(backend_url=backend_url, api_key=api_key)


def save_session(state: SessionState) -> Path:
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2))
    tmp.replace(path)
    return path


def reset_session() -> bool:
    """Delete the session file. Returns True if a file was actually removed."""
    path = session_path()
    if path.exists():
        path.unlink()
        return True
    return False


def update_session(**fields) -> SessionState:
    """Load, apply the given field updates, save, return the new state."""
    state = load_session()
    for k, v in fields.items():
        if hasattr(state, k):
            setattr(state, k, v)
    save_session(state)
    return state
