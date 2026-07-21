# DialogMesh v6 — 实际代码架构

> 基于 api.py + engine.py + api_gateway.py 源码提取。2026-07-21

---

## 一、启动链路

```
start.bat
├─ gateway.exe (Go, :8080)
│   ├─ 读 provider.yaml → 注册 9 厂商
│   ├─ auth_middleware: api_keys 列表
│   ├─ 加权路由 + 断路器 + 健康探针
│   └─ 5min auto-save → state.json (已知会复写 yaml 配置)
│
├─ python start_server.py (FastAPI, :8000)
│   ├─ CognitiveRuntimeEngine(config_path)
│   │   ├─ 40+ 子系统懒加载
│   │   ├─ _init_llm_provider() → config/env → MockProvider
│   │   └─ Mind/Meta/ABC/OCEAN/Inertia/Behavior/Belief/Causal...
│   ├─ startup(): 注入 LLM provider → OpenAIProvider(gateway)
│   ├─ gateway_init(engine) → api_gateway 注册 v6/gateway 代理
│   └─ uvicorn.run(app)
│
└─ npm run preview (Vite, :4173)
    └─ dist/ → 14 页面 SPA
```

---

## 二、API 端点（api.py）

| 路由 | 方法 | 功能 | 实现状态 |
|------|------|------|:---:|
| `/v4/health` | GET | API+引擎健康 | ✅ |
| `/v3/health` | GET | 运行时间 | ✅ |
| `/v3/session` | POST | 创建会话 | ✅ |
| `/v3/session/{id}/message` | POST | **发送消息** | ⚠️ 当前绕过引擎 |
| `/v3/session/{id}/history` | GET | 历史占位 | ✅ |
| `/v4/event` | POST | 引擎事件处理 | ✅ post_event |
| `/v4/ingest` | POST | 文档导入 | ✅ |
| `/v4/checkpoint` | POST | 深度分析触发 | ✅ |
| `/v6/profile` | GET/PUT | 画像 | ✅ |
| `/v6/trace` | GET | 追踪 | ✅ |
| `/v6/abc` | GET | ABC 规则 | ✅ |
| `/v6/mind` | GET | Mind 关系 | ✅ |
| `/v6/*` | GET | 全部 v6 端点 | ✅ |

---

## 三、消息处理流（核心）

### 当前实现（v3_send_message）
```
POST /v3/session/{id}/message
  → post_event(EventRequest)
    → run_in_executor(_engine.on_event)  ← async 化
      → 处理 discourse_tree + concepts + behavior
      → 编译 context_ir
      → _call_llm(event)
        → _last_context 为 None? ← ⚠️ 疑似断点
        → _llm_provider.generate(prompt)
          → OpenAIProvider → gateway → DeepSeek
```

### `_call_llm` 两个守卫
```python
if self._llm_provider is None: return None  # NEVER True（startup 设了）
if self._last_context is None: return None   # ⚠️ 可能这里
```

### LLM provider 配置
```python
# startup() 中
_engine._llm_provider = OpenAIProvider("deepseek", {
    "base_url": "http://127.0.0.1:8080/v1",
    "api_key": "not-needed",
    "model": "deepseek-v4-flash",
})
```

---

## 四、前端架构

```
App.tsx → Layout → ErrorBoundary → 14 pages

核心页面:
  /gateway    → useV6Gateway(15s poll) → GatewayPage
  /chat       → ChatPage (V3 REST) + ProviderSelector
  /profile    → useV6Profile → CognitiveProfilePage
  /meta       → MetaCenterPage
  /settings   → SettingsPage
  /engineering→ EngineeringPage

Chat 数据流:
  ChatPage mount → POST /v3/session → sessionId
  用户输入 → handleUserMessage → sendMessage(sid, content, provider?, model?)
    → POST /v3/session/{id}/message
    → 收到回复 → setMessages([...])
  消息持久化: sessionStorage (跨页保留)
  Provider选择: ProviderSelector → PUT /v6/gateway/active

Gateway 数据流:
  加载 → GET 9 providers → 显示卡片
  展开 → 填写 key/url
  保存 → PUT provider → localStorage 持久化表单
  测试 → POST test → 显示延迟
```

---

## 五、已知断点

| 位置 | 症状 | 推测根因 |
|------|------|---------|
| `_call_llm` L2176 | 174ms 无 token | `_last_context` 为 None |
| `_compile_context` L594 | 不产生 context_ir | 首次调用或 context 为空 |
| `post_event` → `on_event` | 返回 None | _call_llm 返回 None |
| Gateway auto-save | 5min 复写 provider 配置 | state.json 覆盖 yaml |
