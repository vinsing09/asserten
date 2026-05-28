"""Asserten data models — flat dataclasses, frontend-friendly.

Avoid inheritance and unions so a TypeScript frontend can codegen these
1-1. Each model maps to a backend response shape OR a piece of session
state. New fields are additive.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


# ─── Backend response shapes ─────────────────────────────────────────────────


@dataclass
class Agent:
    id: str
    name: str
    business_goal: str = ""
    created_at: str = ""

    @classmethod
    def from_api(cls, d: dict) -> "Agent":
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            business_goal=d.get("business_goal", ""),
            created_at=d.get("created_at", ""),
        )


@dataclass
class AgentVersion:
    id: str
    agent_id: str
    version_number: int = 0
    label: str = ""
    system_prompt: str = ""

    @classmethod
    def from_api(cls, d: dict) -> "AgentVersion":
        return cls(
            id=d["id"],
            agent_id=d["agent_id"],
            version_number=d.get("version_number", 0),
            label=d.get("label", "") or "",
            system_prompt=d.get("system_prompt", ""),
        )


@dataclass
class Patch:
    """One audit-suggested fix the user can accept / reject."""
    id: str
    title: str
    description: str
    severity: str = ""
    target_slot: str = ""
    prompt_patch: str = ""

    @classmethod
    def from_api(cls, d: dict) -> "Patch":
        return cls(
            id=d.get("id", ""),
            title=d.get("title", "") or d.get("issue", "")[:60] or d.get("description", "")[:60],
            description=d.get("description", "") or d.get("rationale", ""),
            severity=d.get("severity", "") or d.get("priority", ""),
            target_slot=d.get("target_slot", ""),
            prompt_patch=d.get("prompt_patch", ""),
        )


@dataclass
class EvalSummary:
    pass_rate: float | None
    total: int = 0
    passed: int = 0
    failed: int = 0
    invalid: bool = False
    judge_error_rate: float = 0.0
    # Phase 1a upstream-lift: distinguishes agent failure from infra failure.
    # validity_warning is a human-readable string when >=20% of results came
    # from non-agent origins; None otherwise. failure_origin_breakdown maps
    # origin name → count (e.g. {"agent": 12, "env": 3, "judge": 1}).
    validity_warning: str | None = None
    failure_origin_breakdown: dict = field(default_factory=dict)
    non_agent_failure_pct: float = 0.0
    # Lineage triplet (handoff item 9): kind + version + locked-case count
    # together identify what was actually run. Two pass rates with different
    # kind / case-mix shouldn't be compared.
    lineage: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict) -> "EvalSummary":
        return cls(
            pass_rate=d.get("pass_rate"),
            total=d.get("total", 0),
            passed=d.get("passed", 0),
            failed=d.get("failed", 0),
            invalid=bool(d.get("invalid", False)),
            judge_error_rate=float(d.get("judge_error_rate", 0.0) or 0.0),
            validity_warning=d.get("validity_warning"),
            failure_origin_breakdown=d.get("failure_origin_breakdown") or {},
            non_agent_failure_pct=float(d.get("non_agent_failure_pct", 0.0) or 0.0),
            lineage=d.get("lineage") or {},
        )


# ── 2026-05-29 scenarios + deploy-gate ─────────────────────────────────


@dataclass
class ScenarioTile:
    """One scenario tile in the customer-facing outcome view."""
    test_case_id: str
    scenario_name: str
    tags: list[str] = field(default_factory=list)
    approved: bool = False
    # passed / failed / judge_error / not_yet_evaluated
    status: str = "not_yet_evaluated"
    failure_origin: str | None = None
    reason: str | None = None
    last_run_id: str | None = None
    agent_excerpt: str | None = None

    @classmethod
    def from_api(cls, d: dict) -> "ScenarioTile":
        return cls(
            test_case_id=d["test_case_id"],
            scenario_name=d.get("scenario_name", ""),
            tags=list(d.get("tags") or []),
            approved=bool(d.get("approved", False)),
            status=d.get("status", "not_yet_evaluated"),
            failure_origin=d.get("failure_origin"),
            reason=d.get("reason"),
            last_run_id=d.get("last_run_id"),
            agent_excerpt=d.get("agent_excerpt"),
        )


@dataclass
class ScenariosView:
    """Backend GET /scenarios response wrapped."""
    version_id: str
    latest_run_id: str | None
    scenarios: list[ScenarioTile] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict) -> "ScenariosView":
        return cls(
            version_id=d.get("version_id", ""),
            latest_run_id=d.get("latest_run_id"),
            scenarios=[ScenarioTile.from_api(s) for s in d.get("scenarios", [])],
            summary=d.get("summary") or {},
        )


@dataclass
class GateResult:
    """Backend POST /deploy-gate response wrapped."""
    verdict: str  # PASSED / BLOCKED / PASSED_NO_APPROVED
    candidate_version_id: str
    baseline_version_id: str
    approved_count: int = 0
    regressions: list[dict] = field(default_factory=list)
    improvements: list[dict] = field(default_factory=list)
    stable_pass: list[dict] = field(default_factory=list)
    stable_fail: list[dict] = field(default_factory=list)
    coverage_gaps: list[dict] = field(default_factory=list)
    reason: str = ""

    @classmethod
    def from_api(cls, d: dict) -> "GateResult":
        return cls(
            verdict=d.get("verdict", "UNKNOWN"),
            candidate_version_id=d.get("candidate_version_id", ""),
            baseline_version_id=d.get("baseline_version_id", ""),
            approved_count=int(d.get("approved_count", 0) or 0),
            regressions=list(d.get("regressions") or []),
            improvements=list(d.get("improvements") or []),
            stable_pass=list(d.get("stable_pass") or []),
            stable_fail=list(d.get("stable_fail") or []),
            coverage_gaps=list(d.get("coverage_gaps") or []),
            reason=d.get("reason", ""),
        )


@dataclass
class FailureCase:
    test_case_id: str
    scenario: str
    assertion_id: str
    reason: str


@dataclass
class OptimizeResult:
    mode: str  # "light" | "deep"
    chosen_version_id: str
    pass_rate: float | None
    delta_vs_input: float | None
    wall_seconds: float
    llm_calls_count: int
    extra: dict = field(default_factory=dict)


# ─── Session state ───────────────────────────────────────────────────────────


@dataclass
class SessionState:
    """Cross-command state for a single asserten run on one agent."""
    backend_url: str
    api_key: str = ""
    agent_id: str = ""
    agent_name: str = ""
    draft_id: str = ""
    v0_version_id: str = ""
    v0_eval_pass_rate: float | None = None
    v1_version_id: str = ""
    v1_eval_pass_rate: float | None = None
    v2a_version_id: str = ""
    v2a_eval_pass_rate: float | None = None
    v2b_version_id: str = ""
    v2b_eval_pass_rate: float | None = None
    v2b_attempts: int = 0
    v2b_last_status: str = ""
    suggested_patches: list[dict] = field(default_factory=list)
    accepted_patch_ids: list[str] = field(default_factory=list)
    candidate_v1_ids: list[str] = field(default_factory=list)
    last_error: str = ""
    # Forensics record of the most recent /asserten-add-tests, /asserten-skip-tests,
    # or /asserten-unskip-tests invocation. Inspect via /asserten-status when an
    # earlier add/skip didn't behave as the customer expected. Shape:
    #   {op, target, at, inserted: [...], errors: [...], skipped: [...],
    #    not_found: [...], unskipped: [...]}
    # — keys present depend on which op ran. `from_dict` ignores unknown keys so
    # forwards/backwards-compatible across plugin upgrades.
    last_test_case_op: dict = field(default_factory=dict)

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionState":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})
