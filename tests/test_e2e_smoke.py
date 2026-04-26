"""E2E smoke test against a live agentops-backend.

Skipped unless ASSERTEN_E2E_BACKEND_URL is set. Hits real endpoints with
a known-good agent_id that exists in the user's local DB. No mocks.

Run manually with:
    ASSERTEN_E2E_BACKEND_URL=http://localhost:8000 \
    ASSERTEN_E2E_AGENT_ID=bea9a565-5546-41c2-87c6-ad6a54c15e7e \
    ASSERTEN_E2E_VERSION_ID=e2e6b9ab-39f7-4aec-adb7-ecf5db48ea42 \
    pytest tests/test_e2e_smoke.py -v
"""
import os

import pytest

from client.api import AssertenClient


BACKEND_URL = os.getenv("ASSERTEN_E2E_BACKEND_URL")
AGENT_ID = os.getenv("ASSERTEN_E2E_AGENT_ID")
VERSION_ID = os.getenv("ASSERTEN_E2E_VERSION_ID")
API_KEY = os.getenv("ASSERTEN_E2E_API_KEY", "")


pytestmark = pytest.mark.skipif(
    not (BACKEND_URL and AGENT_ID and VERSION_ID),
    reason="E2E smoke needs ASSERTEN_E2E_BACKEND_URL + AGENT_ID + VERSION_ID",
)


@pytest.fixture
def client():
    return AssertenClient(backend_url=BACKEND_URL, api_key=API_KEY)


def test_get_agent_works(client):
    a = client.get_agent(AGENT_ID)
    assert a.id == AGENT_ID
    assert a.name


def test_list_versions_returns_at_least_one(client):
    versions = client.list_versions(AGENT_ID)
    assert len(versions) >= 1
    assert any(v.id == VERSION_ID for v in versions)


def test_optimize_light_round_trips(client):
    """Single-candidate ranking → that candidate is the winner by definition."""
    r = client.optimize_light(AGENT_ID, [VERSION_ID])
    assert r.mode == "light"
    assert r.chosen_version_id == VERSION_ID
    assert r.pass_rate is not None
    assert r.delta_vs_input == 0.0  # 1 candidate → median == chosen
    assert r.llm_calls_count == 0


def test_optimize_light_400_on_empty_list(client):
    from client.api import AssertenError
    with pytest.raises(AssertenError) as ei:
        client.optimize_light(AGENT_ID, [])
    assert ei.value.status == 400
