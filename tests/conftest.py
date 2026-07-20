"""Test fixtures for DialogMesh v6.

Provides:
  - engine: mock CognitiveRuntimeEngine
  - api_client: httpx client for API tests
  - is_api_up / is_gateway_up: service health checks
  - mock_llm_response: faked LLM output
"""
import os, sys, pytest, time, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_BASE = "http://127.0.0.1:8000"
GW_BASE = "http://127.0.0.1:8080"
AUTH = {"Authorization": "Bearer dev-token"}


# ── Service health ────────────────────────────
def is_api_up() -> bool:
    try:
        req = urllib.request.Request(f"{API_BASE}/v4/health", headers=AUTH)
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


def is_gateway_up() -> bool:
    try:
        with urllib.request.urlopen(f"{GW_BASE}/v1/health", timeout=2):
            return True
    except Exception:
        return False


def api_get(path: str) -> dict:
    import json
    req = urllib.request.Request(f"{API_BASE}{path}", headers=AUTH)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"ok": True, "status": resp.status, "data": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "data": json.loads(e.read())}
    except Exception as e:
        return {"ok": False, "status": 0, "data": {"error": str(e)}}


# ── Pytest fixtures ───────────────────────────
@pytest.fixture(scope="session")
def api_available():
    """Skip tests if API is not running."""
    if not is_api_up():
        pytest.skip("API not running on :8000 — start with scripts/start_server.py")
    return True


@pytest.fixture(scope="session")
def gateway_available():
    """Skip tests if gateway is not running."""
    if not is_gateway_up():
        pytest.skip("Gateway not running on :8080 — start with gateway.exe")
    return True


@pytest.fixture(scope="session")
def all_services(api_available, gateway_available):
    """All services must be up."""
    return True
