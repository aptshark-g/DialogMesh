# DialogMesh v6 — 前端业务流 (Mermaid)

> 2026-07-20 · 基于 v6 api.py + v6.ts + *.tsx 源码提取

---

## 一、全局启动流

```mermaid
sequenceDiagram
    participant U as 用户
    participant B as start.bat
    participant GW as Gateway(:8080)
    participant API as API(:8000)
    participant FE as 前端(:4173)

    U->>B: 双击 start.bat
    B->>GW: gateway.exe (后台)
    GW-->>GW: 读 provider.yaml → 注册 Provider
    GW-->>GW: auto-save 5min 到 state.json
    B->>API: python start_server.py (后台)
    API-->>API: 读 runtime.yaml → 初始化引擎
    API-->>API: 自动配置 LLM Provider → switch gateway
    B->>FE: npm run preview (后台)
    FE->>API: GET /v3/health → 200?✅:❌
    FE->>API: GET /v4/health → 200?✅:❌
    FE->>API: GET /v6/gateway/providers → 显示列表
```

---

## 二、Gateway 页面 — Provider 管理 ⭐

```mermaid
flowchart TD
    A[打开 /gateway 页面] --> B[useV6Gateway 轮询 15s]
    B --> C{API 在线?}
    C -->|是| D[GET /v6/gateway/providers]
    C -->|否| E[用 DEFAULT_PROVIDERS 兜底]
    D --> F[显示 9 个 Provider 卡片]
    E --> F

    F --> G[用户点击 Provider 展开]
    G --> H[显示 API Key 输入框 + Base URL 输入框]

    H --> I{用户操作}
    I -->|填 key + 点保存| J[PUT /v6/gateway/providers/{name}]
    I -->|点测试连接| K[POST /v6/gateway/providers/{name}/test]
    I -->|点拉取模型| L[POST /v6/gateway/providers/{name}/models]

    J --> M[Gateway PUT /v1/admin/providers/{name}]
    M --> N[更新内存 + 持久化到 provider.yaml]
    N --> O[返回 200 → Provider 卡片变绿]

    K --> P[Gateway → 发 ping 到上游 LLM]
    P --> Q{连通?}
    Q -->|是| R[显示延迟 + ✅]
    Q -->|否| S[显示错误]

    L --> T[Gateway → 调 /models 端点]
    T --> U[显示模型列表]
```

---

## 三、对话 Chat 页面 — REST 流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant FE as ChatPage
    participant API as API(:8000)
    participant ENG as Engine
    participant GW as Gateway(:8080)
    participant LLM as DeepSeek

    U->>FE: 打开 /chat 页面
    FE->>API: POST /v3/session
    API-->>FE: { session_id, ws_url:"" }
    FE->>FE: 连接状态 → ✅ 已连接

    U->>FE: 输入文字，点发送
    FE->>FE: 添加用户消息到列表
    FE->>API: POST /v3/session/{id}/message { content }
    API->>ENG: post_event(EventRequest)
    ENG->>GW: POST /v1/chat/completions
    GW->>LLM: 转发请求 (带 api_key)
    LLM-->>GW: AI 回复
    GW-->>ENG: 回复文本
    ENG-->>API: { reply: "..." }
    API-->>FE: { content: "...", status:"accepted" }
    FE->>FE: 添加 AI 回复到列表
```

---

## 四、配置保存 — 持久化链路

```mermaid
flowchart LR
    A[前端: 填 API Key] --> B[PUT /v6/gateway/providers/deepseek]
    B --> C[Python API: api_gateway.py]
    C --> D{switch :8080 可达?}
    D -->|是| E[PUT /v1/admin/providers/deepseek]
    D -->|否| F[fallback: 返回 builtin 数据]
    E --> G[Manager.Register: 更新内存]
    G --> H[persistProviderToYAML: 写 provider.yaml]
    H --> I[返回 200 OK]

    style H fill:#22c55e,color:#fff
    style I fill:#22c55e,color:#fff
```

**验证**: 关闭浏览器 → 重新打开 → `GET /v6/gateway/providers` → `configured: true`

---

## 五、测试连接 — 发 Ping 流程

```mermaid
sequenceDiagram
    U->>FE: 点击 "测试连接"
    FE->>API: POST /v6/gateway/providers/deepseek/test
    API->>GW: POST /v1/chat/completions { model, messages: [{role:user,content:"ping"}] }
    GW->>LLM: 转发 ping
    LLM-->>GW: pong (任意回复)
    GW-->>API: 200 + latency
    API-->>FE: { healthy: true, latency_ms: 152 }
    FE->>U: 显示 "● 健康 · 152ms"
```

---

## 六、前端 14 页 × 后端交互矩阵

```mermaid
graph LR
    subgraph 只读页
        DASH[Dashboard /] -->|v4/health| API
        PROF[Profile /profile] -->|v6/profile,trace,abc,mind| API
        GRAPH[Graph /graph] -->|v6/graph,objects,relations| API
        PIPE[Pipeline /pipeline] -->|v6/pipeline| API
        DEEP[DeepChain] -->|v6/relations,causal,behavior| API
        ENGR[Engineering] -->|v6/engineering,recursive-map| API
        SESS[Sessions] -->|v6/sessions,persistence| API
    end

    subgraph 读写页
        GW[Gateway ⭐] -->|v6/gateway/* CRUD| API
        CHAT[Chat] -->|v3/session REST| API
        SET[Settings] -->|v6/rules CRUD| API
        META[Meta] -->|v6/meta scan,retrospect,versions| API
        BEH[Behavior] -->|v6/behavior feedback,inertia| API
    end

    subgraph 占位页
        TASK[TaskPlanning] -.->|无API| VOID[纯前端]
    end

    API -->|所有 LLM 调用| GW2[Gateway :8080]
    GW2 -->|路由+断路| LLM[DeepSeek/OpenAI/...]
```

---

## 七、数据流向总结

| 方向 | 路径 | 说明 |
|------|------|------|
| **读** | 前端 → API → 内存/Store | 14 页，40+ 端点 |
| **写(配置)** | 前端 → API → Gateway → provider.yaml | Key/URL 持久化 ✅ |
| **写(对话)** | 前端 → API → Engine → Gateway → LLM | V3 REST ✅ |
| **写(规则)** | 前端 → API → 内存规则库 | Settings 页 |
| **写(画像)** | 前端 → API → Engine Profile | Profile 页 |
| **轮询** | 前端 → API (15s) → Gateway (15s) | 自动健康检查 |

---

## 八、当前功能完成度

```
Gateway 管理:  读 ✅  写 ✅  测试 ✅  持久化 ✅
Chat 对话:    建会话 ✅  发送 ✅  回复 ⚠️ (concepts已修)
Profile:      读 ✅  编辑 ⚠️
Settings:     读 ✅  编辑 ⚠️ (字段名)
Meta:         读 ✅  扫描 ⚠️
Behavior:     读 ✅  反馈 ⚠️
其余 8 页:    读 ✅
```
