"""Batch 2: v6 API deep audit — hit every endpoint, record real behavior."""
import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:8000"

def fetch(path, method="GET", payload=None, timeout=5):
    url = BASE + path
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    if payload:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, body[:300] if body else ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200] if hasattr(e, 'read') else str(e)
    except Exception as e:
        return -1, str(e)[:200]

# Get all endpoints
with urllib.request.urlopen(BASE + "/openapi.json", timeout=5) as resp:
    spec = json.loads(resp.read())

results = []
for path, methods in sorted(spec['paths'].items()):
    for method in methods:
        if method not in ('get', 'post', 'put', 'delete'):
            continue
        # Skip endpoints requiring session_id params for now (GET-only pass)
        status, body = fetch(path, method.upper())
        has_data = len(body.strip()) > 2 and body not in ('[]', '{}', 'null', '""')
        is_error = status >= 400 or status == -1
        results.append({
            "method": method.upper(),
            "path": path,
            "status": status,
            "has_data": has_data,
            "body": body.replace("\n", " ")[:100],
        })

# Summary
ok_real = sum(1 for r in results if r['status'] == 200 and r['has_data'])
ok_empty = sum(1 for r in results if r['status'] == 200 and not r['has_data'])
errors = sum(1 for r in results if r['status'] >= 400 or r['status'] == -1)

print(f"═══ v6 API 核查 ═══")
print(f"  总端点: {len(results)}")
print(f"  ✅ 200+真实数据: {ok_real}")
print(f"  ⚠️ 200+空数据:   {ok_empty}")
print(f"  ❌ 错误/失败:     {errors}")
print()

print("── 空数据 (可能有简化问题) ──")
for r in results:
    if r['status'] == 200 and not r['has_data']:
        print(f"  ⚠️ {r['method']} {r['path']} → empty")
print()
print("── 错误 ──")
for r in results:
    if r['status'] >= 400 or r['status'] == -1:
        print(f"  ❌ {r['method']} {r['path']} → {r['status']}: {r['body'][:80]}")
print()
print("── 真实数据示例 (前10) ──")
shown = 0
for r in results:
    if r['status'] == 200 and r['has_data']:
        print(f"  ✅ {r['method']} {r['path']} → {r['body'][:70]}")
        shown += 1
        if shown >= 10:
            break
