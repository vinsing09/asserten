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
def test_create_agent_draft_sends_auth_header(client):
    route = respx.post(f"{BACKEND}/agents/draft").mock(
        return_value=httpx.Response(200, json={"id": "draft1"})
    )
    out = client.create_agent_draft(
        name="X", raw_system_prompt="prompt", tool_schemas=[]
    )
    assert out["id"] == "draft1"
    assert route.calls.last.request.headers["X-Asserten-Key"] == "secret"


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
    respx.post(f"{BACKEND}/agents/a/versions/v/improvements").mock(
        return_value=httpx.Response(200, json={"job_id": "j1", "status": "queued"})
    )
    j = client.optimize_deep("a", "v", "er1")
    assert j["job_id"] == "j1"


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
