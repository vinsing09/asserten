"""asserten — Claude Code plugin client for the agentops-backend pipeline.

All Python lives under client/ and is pure HTTP + dataclasses. No
Claude-Code dependencies in this package — the slash commands live in
.claude-plugin/commands/ and shell out to a small CLI in this dir.

Public surface (for slash commands and a future TypeScript frontend):

    from client.api import AssertenClient
    from client.session import Session, load_session, save_session
    from client.models import Agent, Patch, EvalSummary, OptimizeResult
    from client.format import render_audit, render_compare_table
"""
__version__ = "0.1.0"
