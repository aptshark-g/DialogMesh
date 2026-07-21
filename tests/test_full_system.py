"""DialogMesh v6 — Full System Test
Usage: 1. start.bat  2. python tests\test_full_system.py
"""
import urllib.request, json

BASE = "http://127.0.0.1:8000"
GW = "http://127.0.0.1:8080"
H = {"Authorization": "Bearer dev-token", "Content-Type": "application/json"}
GH = {"Authorization": "Bearer not-needed", "Content-Type": "application/json"}

P = F = 0

def t(name, fn):
    global P, F
    try:
        fn()
        P += 1
        print(f"  ✅ {name}")
    except Exception as e:
        F += 1
        print(f"  ❌ {name}: {e}")

def ag(p):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{BASE}{p}", headers=H), timeout=8).read())

def ap(p, b):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{BASE}{p}", json.dumps(b).encode(), headers=H, method="POST"), timeout=10).read())

def gg(p):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{GW}{p}", headers=GH), timeout=5).read())

def gp(p, b):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{GW}{p}", json.dumps(b).encode(), headers=GH, method="POST"), timeout=15).read())

print(f"\nDialogMesh v6 — Full System Test\n{'='*50}")

# 1. Health
print("\n═══ 1. Health ═══")
t("Gateway alive", lambda: gg("/v1/health"))
t("API alive", lambda: ag("/v4/health"))

# 2. Gateway
print("\n═══ 2. Gateway ═══")
t("Providers list", lambda: gg("/v1/providers"))
t("DeepSeek active+key", lambda: (
    [p for p in gg("/v1/providers")["providers"] if p["name"]=="deepseek" and p["active"] and p["key_configured"]][0]
))
t("Routing pool API", lambda: gg("/v1/admin/routing"))
t("Diagnostics", lambda: gg("/v1/diagnostics"))

# 3. LLM
print("\n═══ 3. LLM ═══")
t("Gateway→DeepSeek", lambda: (
    d := gp("/v1/chat/completions", {"model":"deepseek-v4-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":20}),
    d["choices"][0]["message"]["content"]
))
t("Routing pool select", lambda: gp("/v1/chat/completions", {"model":"deepseek-v4-flash","messages":[{"role":"user","content":"x"}],"max_tokens":5}))

# 4. API proxy
print("\n═══ 4. API Gateway Proxy ═══")
t("Provider proxy", lambda: ag("/v6/gateway/providers"))
t("Health proxy", lambda: ag("/v6/gateway/health"))

# 5. Chat
print("\n═══ 5. Chat ═══")
t("Create session", lambda: ap("/v3/session", {}))
t("Send message", lambda: (
    d := ap("/v3/session/test/message", {"content": "say hi"}),
    None if len(d.get("content","")) > 3 and "[Error]" not in d["content"]
        and "[引擎无响应]" not in d["content"] else (_ for _ in ()).throw(Exception(f"reply: {d}"))
))

# 6. Core pages
print("\n═══ 6. Core Pages ═══")
for p in ["/v6/profile","/v6/trace","/v6/abc","/v6/mind","/v6/sessions","/v6/persistence",
          "/v6/engineering/modules","/v6/metrics","/v6/router/modes"]:
    t(p.split("/")[-1], lambda p=p: ag(p))

# 7. Write ops
print("\n═══ 7. Write ═══")
t("Checkpoint", lambda: ap("/v4/checkpoint", {}))
t("Feedback", lambda: ap("/v6/feedback", {"turn":1,"correct":True}))

print(f"\n{'='*50}\n  通过: {P}  失败: {F}  总计: {P+F}")
print("  🎉 ALL PASSED" if F==0 else f"  ⚠️  {F} failed")
print(f"{'='*50}\n")
