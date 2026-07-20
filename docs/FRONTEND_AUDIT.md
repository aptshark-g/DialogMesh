# DialogMesh v6 — 前端全链路审计报告

> 时间: 2026-07-20 | 审计方式: 源码追踪 + API 实测

---

## ⚡ 根因一: API 启动失败 (导致一切后续问题)

**证据**: `start.bat` 用 `.venv-test\Scripts\python` 启动 API, 该 venv 的 `pydantic_core` 已损坏。

```
ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
```

**后果**:
- API 进程崩溃 → 前端所有请求连接拒绝
- 前端 `servicesDown=true` → 显示 "未连接" + 用 DEFAULT_PROVIDERS 兜底
- DEFAULT_PROVIDERS 中 key=空 → 前端显示 key 为空
- 每 15 秒轮询尝试连接 → 反复失败 → 用户感知 "一直在刷新"

**修复**: `start.bat` 改用 `python`(系统 Python, 已验证可用)

---

## ⚡ 根因二: 前端直接连 websocket, 无视 ws_url=""

**证据**: 日志显示持续请求 `GET /v4/ws → 404`

**代码路径**:
1. `useWebSocket.ts:279` — `connect(response.session_id, response.ws_url)`
2. `response.ws_url` 现在是 `""` (我们的修复)
3. **但前端 Vite build 缓存旧 JS** — 还是用旧的 URL 生成逻辑

**修复**: 前端需 `npm run build` 清除缓存 + 重启 Vite

---

## ⚡ 根因三: Key 数据流

**实际状态** (API 直连测试 36/36 通过):
- `GET /v6/gateway/providers` → `key_configured: True` ✅
- `PUT /v6/gateway/providers/deepseek` → 200 OK ✅
- 重启后 `key_configured` 仍为 True ✅

**前端显示为空的原因**:
1. API 未启动(根因一) → 后端数据不可达 → 前端用 DEFAULT_PROVIDERS(空 key)
2. 前端 GatewayPage 的 `configForms` 状态为空 → 从 DEFAULT_PROVIDERS 初始化 → key=""

**修复**: 根因一修好后, 前端自然读到真实 key 数据

---

## 📄 前端 14 页业务清单

| 页面 | 路由 | API 数据 | 功能 | 状态 |
|------|------|----------|------|:---:|
| Dashboard | / | v4/health | 概览 | ✅ |
| Chat | /chat | v3/session + message | 对话 | ⚠️ concepts 已修, 待前端更新 |
| ConversationGraph | /graph | (无 API 调用) | 对话图 | ⚠️ 纯前端渲染 |
| CognitiveProfile | /profile | v6/profile | OCEAN 画像 | ✅ |
| TaskPlanning | /tasks | (无 API 调用) | 任务规划 | ⚠️ 纯前端占位 |
| Gateway | /gateway | v6/gateway/* | Provider 管理 | ⚠️ 依赖 API 启动 |
| Pipeline | /pipeline | (无 API 调用) | 管线可视化 | ⚠️ 纯前端渲染 |
| DeepChain | /deepchain | (无 API 调用) | 深层链 | ⚠️ 纯前端渲染 |
| MetaCenter | /meta | v6/meta/* | 元认知 | ⚠️ 依赖引擎 |
| Behavior | /behavior | v6/behavior/* + inertia | 行为发现 | ⚠️ 依赖引擎 |
| Engineering | /engineering | v6/engineering/* | 工程链 | ✅ |
| Sessions | /sessions | v6/sessions + persistence | 会话 | ✅ |
| Settings | /settings | v6/rules | 规则编辑 | ⚠️ editRule 422 |
| NotFound | * | - | 404 | ✅ |

---

## 🔧 修复优先级

1. **`.venv-test` 修复**
   ```
   .venv-test\Scripts\pip uninstall pydantic_core pydantic -y
   .venv-test\Scripts\pip install pydantic
   或: start.bat 改用 python(系统)
   ```

2. **前端清除缓存**
   ```
   cd frontend && npm run build && npm run preview -- --host
   ```

3. **WebSocket 彻底关掉**
   前端 `useWebSocket.ts` 加: `if (!wsUrl) return;`

---

## 📊 当前真实通过率

```
API 端点:     36/36 ✅ (所有端点正常, 包括 key 持久化)
前端渲染:     6/14 ✅ (仅读页面正常, 写操作依赖 API 在线)
系统启动:     1/3  ✅ (Gateway 正常, API 崩溃, 前端缓存)
```
