"""Asserten HTTP client for the agentops-backend.

Each public method maps to one backend endpoint. Returns parsed dataclasses
(see client.models). Caller chooses sync (default) — slash commands shell
out as one-shot scripts and don't need an event loop.

X-Asserten-Key is sent on every mutating request when api_key is set.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from client.models import (
    Agent, AgentVersion, EvalSummary, FailureCase, OptimizeResult, Patch,
)


_HEADER = "X-Asserten-Key"


class AssertenError(Exception):
    """Raised on any non-2xx response. Carries status + body for debugging."""
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"{status} on {url}: {body[:200]}")
        self.status = status
        self.body = body
        self.url = url


class AssertenClient:
    def __init__(self, backend_url: str, api_key: str = "",
                 default_timeout: float = 600.0):
        self.backend_url = backend_url.rstrip("/")
        self.api_key = api_key
        self.default_timeout = default_timeout

    def _headers(self, mutating: bool) -> dict:
        h = {"Content-Type": "application/json"}
        if mutating and self.api_key:
            h[_HEADER] = self.api_key
        return h

    def _request(self, method: str, path: str, *,
                 json_body: dict | None = None,
                 timeout: float | None = None) -> Any:
        url = f"{self.backend_url}{path}"
        mutating = method.upper() != "GET"
        headers = self._headers(mutating)
        with httpx.Client(timeout=timeout or self.default_timeout) as c:
            resp = c.request(method, url, headers=headers, json=json_body)
        if resp.status_code >= 400:
            raise AssertenError(resp.status_code, resp.text, url)
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    # ─── Agents + drafts ──────────────────────────────────────────────────

    def create_agent_draft(self, *, name: str, raw_system_prompt: str,
                           tool_schemas: list[dict],
                           business_goal: str = "",
                           desired_behaviors: list[str] | None = None) -> dict:
        """POST /agents/draft → returns the draft (id is what audit uses).

        Backend's CreateDraftRequest field is `system_prompt`; the asserten
        client uses `raw_system_prompt` to make the user-facing intent
        explicit (this is the user's pre-audit prompt). Translate at the
        boundary so the rest of the app stays consistent.
        """
        return self._request("POST", "/agents/draft", json_body={
            "name": name,
            "system_prompt": raw_system_prompt,
            "tool_schemas": tool_schemas,
            "business_goal": business_goal,
            "desired_behaviors": desired_behaviors or [],
        })

    def audit_draft(self, draft_id: str) -> dict:
        """POST /agents/draft/{id}/audit → suggested_fixes + issues + kind."""
        return self._request("POST", f"/agents/draft/{draft_id}/audit",
                             timeout=300)

    def commit_draft(self, draft_id: str,
                     accepted_fix_ids: list[str]) -> tuple[Agent, str]:
        """POST /agents/draft/{id}/commit → (Agent, v1_version_id).

        Backend returns `{agent_id, version_id, agent_name, fixes_applied,
        system_prompt_preview, kind, ...}`. The version_id is the v1 produced
        by applying the accepted fixes — it's a v1 not v0 because the audit
        already mutated the prompt. We treat it as v1 in asserten and
        synthesize v0 separately if the user wants a raw-prompt baseline.
        """
        d = self._request("POST", f"/agents/draft/{draft_id}/commit",
                          json_body={"accepted_fix_ids": accepted_fix_ids},
                          timeout=300)
        agent = Agent(
            id=d.get("agent_id", ""),
            name=d.get("agent_name", ""),
            business_goal="",
        )
        v1_version_id = d.get("version_id", "")
        return agent, v1_version_id

    def get_agent(self, agent_id: str) -> Agent:
        return Agent.from_api(self._request("GET", f"/agents/{agent_id}"))

    def list_versions(self, agent_id: str) -> list[AgentVersion]:
        rows = self._request("GET", f"/agents/{agent_id}/versions")
        return [AgentVersion.from_api(r) for r in rows]

    # ─── Contract + test cases ────────────────────────────────────────────

    def generate_contract(self, agent_id: str, version_id: str) -> dict:
        return self._request(
            "POST",
            f"/agents/{agent_id}/versions/{version_id}/contract/generate",
            timeout=300,
        )

    def generate_test_cases(self, agent_id: str, version_id: str) -> dict:
        return self._request(
            "POST",
            f"/agents/{agent_id}/versions/{version_id}/test-cases/generate",
            timeout=600,
        )

    # ─── Eval ─────────────────────────────────────────────────────────────

    def run_eval(self, agent_id: str, version_id: str,
                 test_case_source_version_id: str | None = None) -> EvalSummary:
        body: dict = {"run_type": "full"}
        if test_case_source_version_id:
            body["test_case_source_version_id"] = test_case_source_version_id
        d = self._request(
            "POST",
            f"/agents/{agent_id}/versions/{version_id}/eval-runs",
            json_body=body, timeout=1800,
        )
        return EvalSummary.from_api(d.get("summary", {}))

    def list_failures(self, agent_id: str, version_id: str) -> list[FailureCase]:
        """Failures aren't a dedicated endpoint — derive from latest eval row."""
        # v0.1: simplified — the eval endpoint already records to DB.
        # A real failures endpoint would query eval_results joined to test_cases.
        # For now, return [] and rely on the eval summary for counts.
        return []

    # ─── Optimize ─────────────────────────────────────────────────────────

    def optimize_light(self, agent_id: str,
                       candidate_version_ids: list[str]) -> OptimizeResult:
        d = self._request(
            "POST",
            f"/agents/{agent_id}/optimize/light",
            json_body={"candidate_version_ids": candidate_version_ids},
            timeout=60,
        )
        return OptimizeResult(
            mode="light",
            chosen_version_id=d["chosen_version_id"],
            pass_rate=d.get("chosen_pass_rate"),
            delta_vs_input=d.get("delta_vs_median"),
            wall_seconds=d.get("wall_seconds", 0.0),
            llm_calls_count=d.get("llm_calls_count", 0),
            extra={"ranking": d.get("ranking", []),
                   "skipped": d.get("candidates_skipped", 0)},
        )

    def optimize_deep(self, agent_id: str, version_id: str,
                      eval_run_id: str) -> dict:
        """POST /improvements?mode=deep returns a job_id; caller polls.

        Backend takes eval_run_id + mode as query params (not body).
        """
        path = (f"/agents/{agent_id}/versions/{version_id}/improvements"
                f"?eval_run_id={eval_run_id}&mode=deep")
        return self._request("POST", path, timeout=60)

    def poll_improvement_job(self, job_id: str) -> dict:
        return self._request("GET", f"/improvements/jobs/{job_id}")

    def wait_improvement_job(self, job_id: str, *,
                             poll_seconds: float = 30,
                             max_seconds: float = 1800) -> dict:
        """Block until status in {completed, failed} or timeout."""
        t0 = time.monotonic()
        while True:
            job = self.poll_improvement_job(job_id)
            if job.get("status") in ("completed", "failed"):
                return job
            if time.monotonic() - t0 > max_seconds:
                return {**job, "status": "timeout"}
            time.sleep(poll_seconds)

    def apply_improvements(self, agent_id: str, version_id: str,
                           accepted_fix_ids: list[str], eval_run_id: str,
                           accepted_structured: list[dict] | None = None) -> str:
        """Returns the new version_id created by applying the fixes."""
        body = {
            "accepted_fix_ids": accepted_fix_ids,
            "eval_run_id": eval_run_id,
            "accepted_structured": accepted_structured or [],
        }
        d = self._request(
            "POST",
            f"/agents/{agent_id}/versions/{version_id}/improvements/apply",
            json_body=body, timeout=600,
        )
        return d["id"] if "id" in d else d.get("version_id", "")
