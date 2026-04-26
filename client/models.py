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

    @classmethod
    def from_api(cls, d: dict) -> "EvalSummary":
        return cls(
            pass_rate=d.get("pass_rate"),
            total=d.get("total", 0),
            passed=d.get("passed", 0),
            failed=d.get("failed", 0),
            invalid=bool(d.get("invalid", False)),
            judge_error_rate=float(d.get("judge_error_rate", 0.0) or 0.0),
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
    suggested_patches: list[dict] = field(default_factory=list)
    accepted_patch_ids: list[str] = field(default_factory=list)
    candidate_v1_ids: list[str] = field(default_factory=list)
    last_error: str = ""

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionState":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})
