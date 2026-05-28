"""Unit tests for client/api.py — uses respx to mock the backend."""
import pytest
import httpx
import respx

from client.api import AssertenClient, AssertenError
from client.models import EvalSummary


BACKEND = "http://localhost:8000"


@pytest.fixture
def client():
    return AssertenClient(backend_url=BACKEND, api_key="secret")


@respx.mock
def test_create_agent_draft_sends_auth_header_and_correct_field(client):
    route = respx.post(f"{BACKEND}/agents/draft").mock(
        return_value=httpx.Response(200, json={"id": "draft1"})
    )
    out = client.create_agent_draft(
        name="X", raw_system_prompt="prompt", tool_schemas=[]
    )
    assert out["id"] == "draft1"
    assert route.calls.last.request.headers["X-Asserten-Key"] == "secret"
    # Backend wants `system_prompt` — confirm we translate at the boundary.
    body = route.calls.last.request.read().decode()
    assert '"system_prompt": "prompt"' in body
    assert '"raw_system_prompt"' not in body


@respx.mock
def test_get_agent_does_not_send_auth_header(client):
    """GET endpoints don't need the key — middleware doesn't gate them."""
    route = respx.get(f"{BACKEND}/agents/abc").mock(
        return_value=httpx.Response(200, json={"id": "abc", "name": "n"})
    )
    a = client.get_agent("abc")
    assert a.id == "abc"
    assert "X-Asserten-Key" not in route.calls.last.request.headers


@respx.mock
def test_audit_draft_returns_dict(client):
    respx.post(f"{BACKEND}/agents/draft/d1/audit").mock(
        return_value=httpx.Response(200, json={
            "suggested_fixes": [{"id": "f1", "title": "T"}],
            "issues": [],
        })
    )
    out = client.audit_draft("d1")
    assert out["suggested_fixes"][0]["id"] == "f1"


@respx.mock
def test_run_eval_parses_summary(client):
    respx.post(f"{BACKEND}/agents/a/versions/v/eval-runs").mock(
        return_value=httpx.Response(200, json={
            "summary": {"pass_rate": 92, "total": 13, "passed": 12,
                        "failed": 1, "invalid": False, "judge_error_rate": 0}
        })
    )
    s = client.run_eval("a", "v")
    assert isinstance(s, EvalSummary)
    assert s.pass_rate == 92
    assert s.total == 13


@respx.mock
def test_run_eval_propagates_test_case_source(client):
    route = respx.post(f"{BACKEND}/agents/a/versions/v/eval-runs").mock(
        return_value=httpx.Response(200, json={"summary": {"pass_rate": 90}})
    )
    client.run_eval("a", "v", test_case_source_version_id="parent_v")
    body = route.calls.last.request.read().decode()
    assert "parent_v" in body


@respx.mock
def test_run_eval_propagates_environment_id(client):
    """Phase 4 upstream-lift: run_eval can target a specific environment
    (e.g. a hybrid env with per-tool live/stub routing)."""
    route = respx.post(f"{BACKEND}/agents/a/versions/v/eval-runs").mock(
        return_value=httpx.Response(200, json={"summary": {"pass_rate": 90}})
    )
    client.run_eval("a", "v", environment_id="env_hybrid_123")
    body = route.calls.last.request.read().decode()
    assert "env_hybrid_123" in body
    assert "environment_id" in body


@respx.mock
def test_run_eval_omits_environment_id_when_none(client):
    """Backwards-compat: when environment_id is None, the body must NOT
    include the key (old backends would error on unexpected fields)."""
    route = respx.post(f"{BACKEND}/agents/a/versions/v/eval-runs").mock(
        return_value=httpx.Response(200, json={"summary": {"pass_rate": 90}})
    )
    client.run_eval("a", "v")
    body = route.calls.last.request.read().decode()
    assert "environment_id" not in body


@respx.mock
def test_add_user_test_cases_sends_payload_and_returns_result(client):
    route = respx.post(
        f"{BACKEND}/agents/a/versions/v/test-cases/user-provided"
    ).mock(return_value=httpx.Response(200, json={
        "inserted": [{"id": "tc_1", "scenario": "ref"}],
        "errors": [],
    }))
    cases = [{"scenario": "ref", "input_text": "foo", "tool_stubs": {},
              "assertions": [], "obligation_ids": [], "tags": ["happy_path"]}]
    out = client.add_user_test_cases("a", "v", cases)
    assert out["inserted"][0]["id"] == "tc_1"
    body = route.calls.last.request.read().decode()
    assert '"test_cases":' in body
    assert '"scenario": "ref"' in body
    assert route.calls.last.request.headers["X-Asserten-Key"] == "secret"


@respx.mock
def test_skip_test_cases_sends_ids_and_returns_split(client):
    respx.post(f"{BACKEND}/agents/a/versions/v/test-cases/skip").mock(
        return_value=httpx.Response(200, json={
            "skipped": ["tc_1"], "not_found": ["tc_nope"],
        })
    )
    out = client.skip_test_cases("a", "v", ["tc_1", "tc_nope"])
    assert out["skipped"] == ["tc_1"]
    assert out["not_found"] == ["tc_nope"]


@respx.mock
def test_unskip_test_cases_inverse_of_skip(client):
    route = respx.post(f"{BACKEND}/agents/a/versions/v/test-cases/unskip").mock(
        return_value=httpx.Response(200, json={
            "unskipped": ["tc_1"], "not_found": [],
        })
    )
    out = client.unskip_test_cases("a", "v", ["tc_1"])
    assert out["unskipped"] == ["tc_1"]
    body = route.calls.last.request.read().decode()
    assert '"test_case_ids": ["tc_1"]' in body


@respx.mock
def test_add_user_test_cases_4xx_raises_asserten_error(client):
    """422 Unprocessable Entity → AssertenError carries status + body for forensics."""
    respx.post(f"{BACKEND}/agents/a/versions/v/test-cases/user-provided").mock(
        return_value=httpx.Response(422, json={"detail": [
            {"loc": ["body", "test_cases", 0, "tags"], "msg": "value error"}
        ]})
    )
    with pytest.raises(AssertenError) as exc:
        client.add_user_test_cases("a", "v", [{"scenario": "x", "tags": ["fake"]}])
    assert exc.value.status == 422
    assert "value error" in exc.value.body


@respx.mock
def test_add_user_test_cases_404_propagates(client):
    """Unknown agent → 404 from backend → AssertenError preserves URL for debug."""
    respx.post(f"{BACKEND}/agents/nope/versions/v/test-cases/user-provided").mock(
        return_value=httpx.Response(404, json={"detail": "Agent not found"})
    )
    with pytest.raises(AssertenError) as exc:
        client.add_user_test_cases("nope", "v", [{"scenario": "x"}])
    assert exc.value.status == 404
    assert "/agents/nope/" in exc.value.url


@respx.mock
def test_skip_test_cases_5xx_raises(client):
    respx.post(f"{BACKEND}/agents/a/versions/v/test-cases/skip").mock(
        return_value=httpx.Response(503, text="upstream down")
    )
    with pytest.raises(AssertenError) as exc:
        client.skip_test_cases("a", "v", ["tc_1"])
    assert exc.value.status == 503


@respx.mock
def test_get_contract_returns_obligations_and_no_auth_header(client):
    """GET endpoints don't gate on X-Asserten-Key (middleware lets reads through)."""
    route = respx.get(f"{BACKEND}/agents/a/versions/v/contract").mock(
        return_value=httpx.Response(200, json={
            "id": "c1",
            "obligations": [
                {"id": "obl_1", "failure_category": "GOAL_COMPLETION",
                 "text": "by end of conversation"},
                {"id": "obl_2", "failure_category": "REASONING_QUALITY",
                 "text": "apply policy", "auto_injected": True,
                 "source": "auto_injected"},
            ],
            "forbidden_behaviors": [],
            "tool_sequences": [],
        })
    )
    out = client.get_contract("a", "v")
    assert out["obligations"][0]["failure_category"] == "GOAL_COMPLETION"
    assert out["obligations"][1].get("auto_injected") is True
    # GET doesn't send X-Asserten-Key (middleware doesn't require it on reads)
    assert "X-Asserten-Key" not in route.calls.last.request.headers


@respx.mock
def test_get_contract_404_raises(client):
    respx.get(f"{BACKEND}/agents/a/versions/v/contract").mock(
        return_value=httpx.Response(404, json={"detail": "Contract not found"})
    )
    with pytest.raises(AssertenError) as exc:
        client.get_contract("a", "v")
    assert exc.value.status == 404


@respx.mock
def test_add_byoe_test_cases_sends_simple_shape(client):
    route = respx.post(f"{BACKEND}/agents/a/versions/v/test-cases/byoe").mock(
        return_value=httpx.Response(200, json={
            "inserted": [{"id": "tc_1", "scenario": "refund flow"}],
            "errors": [],
        })
    )
    simple = [{
        "input": "I want a refund",
        "agent_should_say": ["order ID"],
        "agent_should_call": ["lookup_order"],
        "agent_should_not": ["approve without verifying"],
    }]
    out = client.add_byoe_test_cases("a", "v", simple)
    assert out["inserted"][0]["scenario"] == "refund flow"
    body = route.calls.last.request.read().decode()
    assert '"agent_should_say":' in body
    assert '"agent_should_call":' in body
    assert '"agent_should_not":' in body
    # Auth header present on mutating request
    assert route.calls.last.request.headers["X-Asserten-Key"] == "secret"


@respx.mock
def test_add_byoe_test_cases_4xx_raises(client):
    respx.post(f"{BACKEND}/agents/a/versions/v/test-cases/byoe").mock(
        return_value=httpx.Response(422, json={"detail": "validation error"})
    )
    with pytest.raises(AssertenError) as exc:
        client.add_byoe_test_cases("a", "v", [{"input": "x"}])
    assert exc.value.status == 422


@respx.mock
def test_optimize_light_parses_result(client):
    respx.post(f"{BACKEND}/agents/a/optimize/light").mock(
        return_value=httpx.Response(200, json={
            "chosen_version_id": "v_top",
            "chosen_pass_rate": 99.0,
            "median_pass_rate": 95.0,
            "delta_vs_median": 4.0,
            "ranking": [{"version_id": "v_top", "pass_rate": 99.0}],
            "candidates_skipped": 0,
            "wall_seconds": 0.01,
            "llm_calls_count": 0,
        })
    )
    r = client.optimize_light("a", ["v_top"])
    assert r.mode == "light"
    assert r.chosen_version_id == "v_top"
    assert r.pass_rate == 99.0
    assert r.delta_vs_input == 4.0
    assert r.llm_calls_count == 0


@respx.mock
def test_optimize_deep_returns_job(client):
    """Backend takes eval_run_id + mode as query params, not body."""
    route = respx.post(
        url__regex=rf"{BACKEND}/agents/a/versions/v/improvements\?.*"
    ).mock(return_value=httpx.Response(200, json={"job_id": "j1", "status": "queued"}))
    j = client.optimize_deep("a", "v", "er1")
    assert j["job_id"] == "j1"
    # confirm both query params on the wire
    last_url = str(route.calls.last.request.url)
    assert "eval_run_id=er1" in last_url
    assert "mode=deep" in last_url


@respx.mock
def test_wait_improvement_job_returns_when_completed(client, monkeypatch):
    # Avoid real sleep — patch the module's time.sleep, not the fixture's name.
    import client as _client_mod  # noqa: F401  (kept for clarity)
    from client import api as api_mod
    monkeypatch.setattr(api_mod.time, "sleep", lambda _: None)

    poll_responses = iter([
        httpx.Response(200, json={"status": "running"}),
        httpx.Response(200, json={"status": "running"}),
        httpx.Response(200, json={"status": "completed", "result": "ok"}),
    ])
    respx.get(f"{BACKEND}/improvements/jobs/j1").mock(
        side_effect=lambda req: next(poll_responses)
    )
    j = client.wait_improvement_job("j1", poll_seconds=0)
    assert j["status"] == "completed"


@respx.mock
def test_4xx_raises_asserten_error(client):
    respx.post(f"{BACKEND}/agents/draft").mock(
        return_value=httpx.Response(400, text='{"detail": "bad input"}')
    )
    with pytest.raises(AssertenError) as ei:
        client.create_agent_draft(name="x", raw_system_prompt="", tool_schemas=[])
    assert ei.value.status == 400
    assert "bad input" in ei.value.body


@respx.mock
def test_401_on_missing_auth_raises(client):
    respx.post(f"{BACKEND}/agents/draft").mock(
        return_value=httpx.Response(401, text='{"detail": "missing key"}')
    )
    c = AssertenClient(backend_url=BACKEND, api_key="")  # no key
    with pytest.raises(AssertenError) as ei:
        c.create_agent_draft(name="x", raw_system_prompt="", tool_schemas=[])
    assert ei.value.status == 401


@respx.mock
def test_apply_improvements_returns_new_version_id(client):
    respx.post(f"{BACKEND}/agents/a/versions/v/improvements/apply").mock(
        return_value=httpx.Response(200, json={"id": "v_new"})
    )
    new_id = client.apply_improvements(
        "a", "v", accepted_fix_ids=["f1"], eval_run_id="er1",
    )
    assert new_id == "v_new"
