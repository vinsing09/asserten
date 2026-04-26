"""Live end-to-end integration tests against a running agentops-backend.

Skipped unless ASSERTEN_E2E_BACKEND_URL + ASSERTEN_E2E_API_KEY are set.
Real backend, real LLM calls, real money (~$2-4 per test).

Real backend semantics confirmed by /tmp/asserten_full_probe:
- One commit creates BOTH v0 ('original') AND v1 ('Audited') on the
  same agent automatically. Look up v0 from list_versions.
- /test-cases/generate requires /contract/generate to have been called
  on the version first. We always prepare on v1; v0 reuses v1's tests
  via the test_case_source_version_id parameter on eval-runs.

Scenarios (mimicking real user input paths):
  1. Fresh ingest → audit → select ALL → prepare → eval v0 + v1
  2. Fresh ingest → audit → select FEW (subset) → prepare → eval v0 + v1
  3. Fresh ingest → audit → select NONE → prepare → eval v0 (== v1)
  4. LIGHT optimize on existing multi-candidate agent (bea9a565)
  5. Auth: 401 without key, 200 with key
  6. Multiple drafts isolation
  7. Patch-selection parser stress (free-form inputs)
"""
import json
import os
import time
from pathlib import Path

import httpx
import pytest

from client.api import AssertenClient, AssertenError
from client.format import parse_patch_selection
from client.models import Patch


BACKEND = os.getenv("ASSERTEN_E2E_BACKEND_URL")
API_KEY = os.getenv("ASSERTEN_E2E_API_KEY", "")
SAMPLE_AGENT_PATH = Path(__file__).parent.parent / "examples" / "sample_agent.json"
EXISTING_AGENT_ID = os.getenv("ASSERTEN_E2E_AGENT_ID",
                               "bea9a565-5546-41c2-87c6-ad6a54c15e7e")
EXISTING_VERSION_ID = os.getenv("ASSERTEN_E2E_VERSION_ID",
                                 "e2e6b9ab-39f7-4aec-adb7-ecf5db48ea42")


pytestmark = pytest.mark.skipif(
    not BACKEND, reason="needs ASSERTEN_E2E_BACKEND_URL"
)


@pytest.fixture
def client() -> AssertenClient:
    return AssertenClient(backend_url=BACKEND, api_key=API_KEY)


@pytest.fixture
def sample_agent() -> dict:
    return json.loads(SAMPLE_AGENT_PATH.read_text())


def _ingest_audit_commit(client: AssertenClient, sample: dict, label: str,
                         pick_answer: str) -> dict:
    """One full happy-path step: ingest → audit → user picks → commit → prepare.

    Returns dict with timings + the resulting v0_id, v1_id, agent_id.
    `pick_answer` is whatever the user would type at the patch-selection
    prompt: 'all' / 'none' / '1,3,5'.
    """
    out: dict = {"label": label, "pick_answer": pick_answer}
    t = time.monotonic()
    draft = client.create_agent_draft(
        name=f"{sample['name']} ({label})",
        raw_system_prompt=sample["raw_system_prompt"],
        tool_schemas=sample["tool_schemas"],
        business_goal=sample["business_goal"],
        desired_behaviors=sample["desired_behaviors"],
    )
    out["t_ingest"] = time.monotonic() - t
    out["draft_id"] = draft["id"]
    print(f"  ingest: {draft['id'][:8]} ({out['t_ingest']:.1f}s)")

    t = time.monotonic()
    audit = client.audit_draft(draft["id"])
    out["t_audit"] = time.monotonic() - t
    out["fixes"] = audit.get("suggested_fixes", [])
    out["inferred_kind"] = audit.get("inferred_kind")
    print(f"  audit: {len(out['fixes'])} fixes, kind={out['inferred_kind']} "
          f"({out['t_audit']:.1f}s)")

    indices = parse_patch_selection(pick_answer, len(out["fixes"]))
    accepted = [out["fixes"][i]["id"] for i in indices]
    out["accepted_count"] = len(accepted)
    print(f"  user picks '{pick_answer}' → {len(accepted)}/{len(out['fixes'])} fixes")

    t = time.monotonic()
    agent, v1_id = client.commit_draft(draft["id"], accepted_fix_ids=accepted)
    versions = client.list_versions(agent.id)
    v0_id = next((v.id for v in versions if v.version_number == 0), v1_id)
    out["t_commit"] = time.monotonic() - t
    out["agent_id"] = agent.id
    out["v0_id"] = v0_id
    out["v1_id"] = v1_id
    print(f"  commit: agent={agent.id[:8]} v0={v0_id[:8]} v1={v1_id[:8]} "
          f"({out['t_commit']:.1f}s)")

    t = time.monotonic()
    contract = client.generate_contract(agent.id, v1_id)
    out["t_contract"] = time.monotonic() - t
    out["n_obligations"] = len(contract.get("obligations", []))
    print(f"  contract: {out['n_obligations']} obligations ({out['t_contract']:.1f}s)")

    t = time.monotonic()
    tcs = client.generate_test_cases(agent.id, v1_id)
    out["t_testcases"] = time.monotonic() - t
    out["n_testcases"] = tcs.get("count", 0) if isinstance(tcs, dict) else 0
    print(f"  test_cases: {out['n_testcases']} generated ({out['t_testcases']:.1f}s)")
    return out


# ─── Scenario 1: select ALL ──────────────────────────────────────────────────


def test_scenario_1_select_all(client, sample_agent):
    print("\n[SCENARIO 1] select ALL")
    r = _ingest_audit_commit(client, sample_agent, "select_all", "all")
    assert r["accepted_count"] == len(r["fixes"])
    assert r["v0_id"] != r["v1_id"]
    assert r["n_testcases"] >= 1

    t = time.monotonic()
    v0 = client.run_eval(r["agent_id"], r["v0_id"], test_case_source_version_id=r["v1_id"])
    print(f"  eval v0: pr={v0.pass_rate}% ({time.monotonic()-t:.1f}s)")
    t = time.monotonic()
    v1 = client.run_eval(r["agent_id"], r["v1_id"], test_case_source_version_id=r["v1_id"])
    print(f"  eval v1: pr={v1.pass_rate}% ({time.monotonic()-t:.1f}s)")
    if v0.pass_rate is not None and v1.pass_rate is not None:
        delta = v1.pass_rate - v0.pass_rate
        print(f"  → Δ vs v0: {delta:+.1f}pp")


# ─── Scenario 2: select FEW ──────────────────────────────────────────────────


def test_scenario_2_select_few(client, sample_agent):
    print("\n[SCENARIO 2] select FEW (first half)")
    r = _ingest_audit_commit(client, sample_agent, "select_few", "1,2")
    assert r["accepted_count"] == 2
    assert r["v0_id"] != r["v1_id"]
    v0 = client.run_eval(r["agent_id"], r["v0_id"], test_case_source_version_id=r["v1_id"])
    v1 = client.run_eval(r["agent_id"], r["v1_id"], test_case_source_version_id=r["v1_id"])
    print(f"  v0={v0.pass_rate}% v1={v1.pass_rate}%")


# ─── Scenario 3: select NONE ─────────────────────────────────────────────────


def test_scenario_3_select_none(client, sample_agent):
    """User declines all patches → v0 == v1 functionally (commit applies 0 fixes)."""
    print("\n[SCENARIO 3] select NONE")
    r = _ingest_audit_commit(client, sample_agent, "select_none", "none")
    assert r["accepted_count"] == 0
    # When 0 fixes are applied, backend may still create a v1 (with no diff)
    # or return the same id as v0 — accept either shape.
    print(f"  v0={r['v0_id'][:8]} v1={r['v1_id'][:8]}")
    v_any = client.run_eval(r["agent_id"], r["v1_id"], test_case_source_version_id=r["v1_id"])
    print(f"  eval (v1 with 0 fixes): pr={v_any.pass_rate}%")


# ─── Scenario 4: LIGHT optimize on existing agent ────────────────────────────


def test_scenario_4_light_optimize(client):
    print("\n[SCENARIO 4] LIGHT optimize on existing agent")
    r = client.optimize_light(EXISTING_AGENT_ID, [EXISTING_VERSION_ID])
    print(f"  chosen: {r.chosen_version_id[:8]} pr={r.pass_rate}% "
          f"Δ={r.delta_vs_input:+.1f}pp llm_calls={r.llm_calls_count} "
          f"wall={r.wall_seconds:.3f}s")
    assert r.chosen_version_id == EXISTING_VERSION_ID
    assert r.llm_calls_count == 0
    assert r.wall_seconds < 1.0


def test_scenario_4b_light_optimize_with_multiple_candidates(client):
    """If the existing agent has multiple v1 candidates from past sweeps,
    LIGHT picks the best one. This is the realistic case."""
    print("\n[SCENARIO 4b] LIGHT optimize across all extant versions")
    versions = client.list_versions(EXISTING_AGENT_ID)
    candidate_ids = [v.id for v in versions]
    print(f"  agent has {len(candidate_ids)} candidate versions")
    if len(candidate_ids) < 2:
        pytest.skip("need >=2 candidates")
    r = client.optimize_light(EXISTING_AGENT_ID, candidate_ids)
    print(f"  chose {r.chosen_version_id[:8]} @ {r.pass_rate}% "
          f"out of {r.extra.get('candidates_considered', 'n/a')} considered "
          f"(skipped {r.extra.get('skipped', 0)})")
    assert r.chosen_version_id in candidate_ids


# ─── Scenario 5: Auth ────────────────────────────────────────────────────────


def test_scenario_5_auth_blocks_without_key():
    print("\n[SCENARIO 5] auth gate")
    no_key = AssertenClient(backend_url=BACKEND, api_key="")
    a = no_key.get_agent(EXISTING_AGENT_ID)
    print(f"  GET without key: ok ({a.id[:8]})")
    with pytest.raises(AssertenError) as ei:
        no_key.optimize_light(EXISTING_AGENT_ID, [EXISTING_VERSION_ID])
    print(f"  POST without key: {ei.value.status} (expected 401)")
    assert ei.value.status == 401


def test_scenario_5b_auth_allows_with_key(client):
    print("\n[SCENARIO 5b] auth allows with key")
    r = client.optimize_light(EXISTING_AGENT_ID, [EXISTING_VERSION_ID])
    assert r.chosen_version_id == EXISTING_VERSION_ID
    print(f"  POST with key: ok ({r.pass_rate}%)")


# ─── Scenario 6: Draft isolation ─────────────────────────────────────────────


def test_scenario_6_two_drafts_dont_share_state(client, sample_agent):
    print("\n[SCENARIO 6] multi-draft isolation")
    d1 = client.create_agent_draft(
        name=sample_agent['name'] + " A",
        raw_system_prompt=sample_agent["raw_system_prompt"],
        tool_schemas=sample_agent["tool_schemas"],
        business_goal=sample_agent["business_goal"],
    )
    d2 = client.create_agent_draft(
        name=sample_agent['name'] + " B",
        raw_system_prompt=sample_agent["raw_system_prompt"],
        tool_schemas=sample_agent["tool_schemas"],
        business_goal=sample_agent["business_goal"],
    )
    assert d1["id"] != d2["id"]
    print(f"  draft A={d1['id'][:8]} B={d2['id'][:8]}")


# ─── Scenario 7: Patch selection parser stress ───────────────────────────────


@pytest.mark.parametrize("answer,expected_count", [
    ("all", 5), ("ALL", 5), ("*", 5),
    ("none", 0), ("skip", 0), ("", 0),
    ("1", 1), ("3", 1),
    ("1,2,3", 3), ("1, 2, 3", 3), ("1 2 3", 3),
    ("1,1,2,2", 2),  # dedup
    ("1,99,2", 2),   # out-of-range dropped
    ("1,foo,2", 2),  # garbage dropped
])
def test_scenario_7_patch_selection_parser(answer, expected_count):
    """Parser handles every reasonable user reply shape."""
    indices = parse_patch_selection(answer, n_patches=5)
    assert len(indices) == expected_count
