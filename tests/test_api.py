"""API endpoint smoke tests — verify all core routes respond correctly.

Run:  .venv-test\\Scripts\\python -m pytest tests/test_api.py -v
      .venv-test\\Scripts\\python -m pytest tests/test_api.py -v -m "smoke"
"""
import pytest, urllib.request, urllib.error, json

API_BASE = "http://127.0.0.1:8000"
GW_BASE = "http://127.0.0.1:8080"
AUTH = {"Authorization": "Bearer dev-token"}


def api_get(path: str) -> dict:
    req = urllib.request.Request(f"{API_BASE}{path}", headers=AUTH)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"ok": True, "status": resp.status, "data": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "data": json.loads(e.read())}
    except Exception as e:
        return {"ok": False, "status": 0, "data": {"error": str(e)}}


# ── Health ────────────────────────────────────
class TestHealth:
    @pytest.mark.smoke
    def test_api_health(self, api_available):
        r = api_get("/v4/health")
        assert r["ok"], f"Health failed: {r['data']}"
        assert "api" in r["data"]

    @pytest.mark.smoke
    def test_api_v3_health(self, api_available):
        r = api_get("/v3/health")
        assert r["ok"], f"v3 health failed: {r}"

    @pytest.mark.gateway
    def test_gateway_health(self, gateway_available):
        import urllib.request
        req = urllib.request.Request(f"{GW_BASE}/v1/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200


# ── Core pages ────────────────────────────────
class TestCorePages:
    CORE = ["/v6/profile", "/v6/trace", "/v6/abc", "/v6/mind",
            "/v6/sessions", "/v6/persistence"]

    @pytest.mark.smoke
    @pytest.mark.parametrize("path", CORE)
    def test_core_page(self, api_available, path):
        r = api_get(path)
        assert r["ok"], f"{path}: {r['status']} → {r['data']}"


# ── Gateway proxy ─────────────────────────────
class TestGateway:
    GW = ["/v6/gateway/providers", "/v6/gateway/config", "/v6/gateway/health",
          "/v6/gateway/stats", "/v6/gateway/usage"]

    @pytest.mark.api
    @pytest.mark.parametrize("path", GW)
    def test_gateway_proxy(self, all_services, path):
        r = api_get(path)
        assert r["ok"], f"{path}: {r['status']}"

    @pytest.mark.api
    def test_provider_has_deepseek(self, all_services):
        r = api_get("/v6/gateway/providers")
        providers = [p["name"] for p in r["data"].get("providers", [])]
        assert "deepseek" in providers, f"No deepseek in: {providers}"

    @pytest.mark.api
    def test_deepseek_healthy(self, all_services):
        r = api_get("/v6/gateway/providers")
        for p in r["data"].get("providers", []):
            if p["name"] == "deepseek":
                assert p.get("active") or p.get("healthy"), "DeepSeek not active/healthy"


# ── Monitor ───────────────────────────────────
class TestMonitor:
    @pytest.mark.api
    def test_dashboard(self, api_available):
        import urllib.request
        req = urllib.request.Request(f"{API_BASE}/v6/monitor/dashboard")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            body = resp.read().decode()
            assert "DialogMesh" in body

    @pytest.mark.api
    def test_interactions(self, api_available):
        r = api_get("/v6/monitor/interactions")
        assert r["ok"], f"Monitor failed: {r['data']}"
        assert "recent" in r["data"]

    @pytest.mark.api
    def test_stats(self, api_available):
        r = api_get("/v6/monitor/stats")
        assert r["ok"]
        assert "total_requests" in r["data"]

    @pytest.mark.api
    def test_traces(self, api_available):
        r = api_get("/v6/monitor/traces")
        assert r["ok"]


# ── P1/P2 endpoints ───────────────────────────
class TestAdvancedEndpoints:
    P1P2 = ["/v6/degradation", "/v6/causal-chain", "/v6/sync",
            "/v6/causal", "/v6/ttl", "/v6/subgraph/cache", "/v6/audit"]

    @pytest.mark.api
    @pytest.mark.parametrize("path", P1P2)
    def test_p1p2_endpoint(self, api_available, path):
        r = api_get(path)
        assert r["ok"], f"{path}: {r['status']} → {r.get('data')}"


# ── Diagnostics ───────────────────────────────
class TestDiagnostics:
    @pytest.mark.gateway
    def test_gateway_diagnostics(self, gateway_available):
        import urllib.request, json
        req = urllib.request.Request(f"{GW_BASE}/v1/diagnostics")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            assert "providers" in data
            assert "problems_detected" in data


# ── Auth ──────────────────────────────────────
class TestAuth:
    def test_unauthorized(self):
        import urllib.request, urllib.error
        req = urllib.request.Request(f"{API_BASE}/v6/profile")
        try:
            urllib.request.urlopen(req, timeout=2)
            pytest.fail("Should require auth")
        except urllib.error.HTTPError as e:
            assert e.code == 401

    def test_authorized(self, api_available):
        r = api_get("/v6/profile")
        assert r["ok"]


# ── CORS ──────────────────────────────────────
class TestCORS:
    def test_options_preflight(self, api_available):
        import urllib.request
        req = urllib.request.Request(f"{API_BASE}/v6/profile", method="OPTIONS")
        req.add_header("Origin", "http://localhost:4173")
        req.add_header("Access-Control-Request-Method", "GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert resp.status == 200
            assert "Access-Control-Allow-Origin" in resp.headers
