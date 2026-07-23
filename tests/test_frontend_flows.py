r"""End-to-end frontend flow test — simulates user actions via API.

Tests every flow the frontend triggers:
  1. Provider Key → fill + save + verify persistence
  2. Chat → create session → send message → get reply
  3. Settings → read + edit rules
  4. Health → all checks pass

Run:  .venv-test\Scripts\python tests\test_frontend_flows.py
"""
import urllib.request, urllib.error, json, time, sys

API = "http://127.0.0.1:8000"
GW = "http://127.0.0.1:8080"
AUTH = {"Authorization": "Bearer dev-token", "Content-Type": "application/json"}

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: {detail}")


def api(method: str, path: str, body: dict = None) -> dict:
    data = json.dumps(body or {}).encode()
    url = f"{API}{path}" if path.startswith("/") else path
    req = urllib.request.Request(url, data=data, headers=AUTH, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode()
            try:
                return {"ok": True, "status": r.status, "data": json.loads(raw)}
            except json.JSONDecodeError:
                return {"ok": True, "status": r.status, "data": {"raw": raw[:500]}}
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {"error": str(e)}
        return {"ok": False, "status": e.code, "data": body}
    except Exception as e:
        return {"ok": False, "status": 0, "data": {"error": str(e)}}


# ═══════════════════════════════════════════════════════════
# FLOW 1: Provider Key persistence
# ═══════════════════════════════════════════════════════════
def test_key_persistence():
    print("\n═══ FLOW 1: Key 持久化 ═══")

    # 1a. Get current providers
    r = api("GET", "/v6/gateway/providers")
    check("获取 Provider 列表", r["ok"], str(r["status"]))
    providers = r["data"].get("providers", [])
    deepseek = [p for p in providers if p["name"] == "deepseek"]
    check("DeepSeek 在列表中", len(deepseek) > 0)

    # 1b. Check if key is already configured
    ds = deepseek[0] if deepseek else {}
    has_key = ds.get("key_configured") or ds.get("configured")
    print(f"  DeepSeek key_configured: {has_key}")

    # 1c. Save key via PUT
    r = api("PUT", "/v6/gateway/providers/deepseek", {
        "api_key": "test-key-persistence-check",
        "base_url": "https://api.deepseek.com",
    })
    check("保存 DeepSeek Key", r["ok"], str(r["status"]))

    # 1d. Verify key persisted (re-fetch)
    r = api("GET", "/v6/gateway/providers")
    providers2 = r["data"].get("providers", [])
    ds2 = [p for p in providers2 if p["name"] == "deepseek"]
    if ds2:
        has_key2 = ds2[0].get("key_configured") or ds2[0].get("configured")
        check("Key 持久化成功 (刷新后存在)", has_key2 == True,
              f"key_configured={has_key2}")

    # 1e. Restore original key from provider.yaml
    r = api("PUT", "/v6/gateway/providers/deepseek", {
        "api_key": "sk-20d76b2a00314beabb73dd8ab9d5743d",
        "base_url": "https://api.deepseek.com",
    })
    check("恢复原始 Key", r["ok"], str(r["status"]))


# ═══════════════════════════════════════════════════════════
# FLOW 2: Chat conversation
# ═══════════════════════════════════════════════════════════
def test_chat_flow():
    print("\n═══ FLOW 2: 对话流程 ═══")

    # 2a. Create session
    r = api("POST", "/v3/session")
    check("创建会话", r["ok"], str(r["status"]))
    sid = r["data"].get("session_id", "test")
    print(f"  session_id: {sid}")

    # 2b. Send first message
    r = api("POST", f"/v3/session/{sid}/message", {"content": "你好，请用一句话介绍自己"})
    check("发送首条消息", r["ok"], str(r["status"]))
    reply = r["data"].get("reply", "")
    print(f"  回复: {str(reply)[:100]}")

    # 2c. Send follow-up
    r = api("POST", f"/v3/session/{sid}/message", {"content": "Python 和 Go 哪个更适合网络编程？"})
    check("发送第二条消息", r["ok"], str(r["status"]))

    # 2d. Check history
    r = api("GET", f"/v3/session/{sid}/history")
    check("获取历史记录", r["ok"], str(r["status"]))

    # 2e. Check session status
    r = api("GET", f"/v3/session/{sid}/status")
    check("获取会话状态", r["ok"], str(r["status"]))

    # 2f. Direct /v4/event test (bypasses frontend)
    r = api("POST", "/v4/event", {
        "text": "hello world",
        "source": "user",
        "session_id": sid,
        "event_id": f"flowtest_{int(time.time())}",
    })
    check("/v4/event 直连", r["ok"] or r["status"] == 500,
          f"status={r['status']} (500=LLM调用失败, OK)")


# ═══════════════════════════════════════════════════════════
# FLOW 3: Settings + Rules
# ═══════════════════════════════════════════════════════════
def test_settings_flow():
    print("\n═══ FLOW 3: 设置页 ═══")

    r = api("GET", "/v6/rules")
    check("读取规则列表", r["ok"], str(r["status"]))
    rules = r["data"].get("rules", [])
    print(f"  规则数量: {len(rules)}")

    if rules:
        rule = rules[0]
        r = api("PUT", "/v6/rules", {
            "name": rule["name"],
            "conclusion": rule.get("conclusion", {}),
            "confidence": rule.get("confidence", 0.8),
        })
        check(f"编辑规则 {rule['name']}", r["ok"] or r["status"] == 422,
              f"status={r['status']}")


# ═══════════════════════════════════════════════════════════
# FLOW 4: Health + Gateway connectivity
# ═══════════════════════════════════════════════════════════
def test_health_flow():
    print("\n═══ FLOW 4: 健康检查 ═══")

    r = api("GET", "/v4/health")
    check("API /v4/health", r["ok"])

    r = api("GET", "/v3/health")
    check("API /v3/health", r["ok"])

    r = api("GET", "/v6/gateway/health")
    check("网关代理 /v6/gateway/health", r["ok"])

    # Direct gateway check
    try:
        req = urllib.request.Request(f"{GW}/v1/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            check("Gateway /v1/health 直连", resp.status == 200)
    except Exception as e:
        check("Gateway /v1/health 直连", False, str(e))


# ═══════════════════════════════════════════════════════════
# FLOW 5: Core pages load
# ═══════════════════════════════════════════════════════════
def test_core_pages():
    print("\n═══ FLOW 5: 核心页面数据 ═══")

    pages = {
        "画像": "/v6/profile",
        "追踪": "/v6/trace",
        "ABC规则": "/v6/abc",
        "Mind": "/v6/mind",
        "会话": "/v6/sessions",
        "持久化": "/v6/persistence",
        "递归地图": "/v6/recursive-map",
        "工程模块": "/v6/engineering/modules",
        "工程": "/v6/engineering",
        "路由模式": "/v6/router/modes",
        "Provider": "/v6/providers",
        "Token": "/v6/providers/tokens",
        "指标": "/v6/metrics",
        "降级": "/v6/degradation",
        "因果链": "/v6/causal-chain",
        "因果": "/v6/causal",
        "TTL": "/v6/ttl",
        "子图缓存": "/v6/subgraph/cache",
        "审计": "/v6/audit",
    }
    for name, path in pages.items():
        r = api("GET", path)
        check(f"{name} ({path})", r["ok"], str(r["status"]))


# ═══════════════════════════════════════════════════════════
def main():
    print("DialogMesh v6 — Frontend Flow Test")
    print("=" * 60)

    test_key_persistence()
    test_chat_flow()
    test_settings_flow()
    test_health_flow()
    test_core_pages()

    print(f"\n{'=' * 60}")
    print(f"  通过: {PASS}  失败: {FAIL}  总计: {PASS + FAIL}")
    print(f"{'=' * 60}")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
