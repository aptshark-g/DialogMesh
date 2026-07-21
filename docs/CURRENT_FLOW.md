# DialogMesh v6 — 当前完整业务流 (2026-07-21)

## 端到端请求流

```mermaid
sequenceDiagram
    participant U as 用户浏览器
    participant FE as 前端 (:4173)
    participant API as API (:8000)
    participant ENG as CognitiveEngine
    participant GW as Gateway (:8080)
    participant LLM as DeepSeek

    Note over U,LLM: ═══ 启动 ═══
    U->>FE: start.bat
    FE->>FE: Vite build → dist/
    API->>API: CognitiveRuntimeEngine(config)
    API->>API: GatewayLLMProvider(deepseek, :8080)
    API->>API: gateway_init → v6/gateway 代理
    GW->>GW: ParseFile(provider.yaml) → 注册9厂商
    GW->>GW: Bootstrap → deepseek active+key
    GW->>GW: auto-save 5min → state.json

    Note over U,LLM: ═══ 页面加载 ═══
    U->>FE: 打开 /gateway
    FE->>API: GET /v6/gateway/providers
    API->>GW: GET /v1/providers
    GW-->>API: [{ deepseek:active+key, lmstudio:inactive, ... }]
    API-->>FE: 9 providers
    FE->>FE: 渲染 Provider 卡片

    Note over U,LLM: ═══ 配置 API Key ═══
    U->>FE: 填 DeepSeek Key → 点保存
    FE->>API: PUT /v6/gateway/providers/deepseek {api_key}
    API->>GW: PUT /v1/admin/providers/deepseek
    GW->>GW: Unregister + Register(新cfg)
    GW->>GW: persistProviderToYAML → provider.yaml ✅
    GW-->>API: 200 {persisted:true}
    API-->>FE: 200 → Provider 变绿 ✅

    Note over U,LLM: ═══ 聊天 ═══
    U->>FE: 打开 /chat
    FE->>API: POST /v3/session
    API-->>FE: {session_id, ws_url}

    U->>FE: 输入文字 → 发送
    FE->>API: POST /v3/session/{id}/message {content}
    API->>ENG: post_event(EventRequest)
    ENG->>ENG: on_event(event_ir)
    ENG->>ENG:   → discourse_tree.feed()
    ENG->>ENG:   → compile_context() → CrossDomainContextIR
    ENG->>ENG:   → _call_llm(event)
    ENG->>GW: GatewayLLMProvider.generate() → POST /v1/chat/completions?provider=deepseek
    GW->>GW: getRoutingProvider() → deepseek
    GW->>LLM: POST https://api.deepseek.com/v1/chat/completions
    LLM-->>GW: {choices: [{message: {content: "..."}}]}
    GW-->>ENG: GenerateResponse
    ENG-->>API: {response: "LLM reply"}
    API-->>FE: {content: "LLM reply"}
    FE->>FE: 显示回复 + 正确答案/错误/注释按钮

    Note over U,LLM: ═══ 断路降级 ═══
    GW->>GW: DeepSeek 返回 503 → CircuitBreaker OPEN
    ENG->>GW: 下次请求
    GW->>GW: gracefulDegradation → getRoutingCandidates()
    GW->>GW:   试下一个 active+key provider
    GW->>LLM: 降级到备选厂商
    LLM-->>GW: 回复
    GW-->>ENG: 200 → 前端提示 "已切换"
```

---

## 组件关系图

```mermaid
graph TD
    subgraph FRONTEND["前端 (Vite + React)"]
        CHAT[ChatPage · zustand store · WS+REST]
        GWPG[GatewayPage · localStorage · 厂商管理]
        PROF[ProfilePage · OCEAN雷达图]
        TRACE[TracePage · 追踪]
        ABC[ABC规则]
        MIND[Mind]
        META[MetaCenter]
        SET[Settings]
    end

    subgraph API["FastAPI (:8000)"]
        V3[V3 Session · 创建/消息/历史]
        V4[V4 Event · post_event]
        V6[V6 CRUD · profile/trace/abc/mind/...]
        GW_PROXY[V6 Gateway · providers/config/usage/stats]
    end

    subgraph ENGINE["CognitiveRuntimeEngine"]
        ON_EVENT[on_event · 事件处理]
        COMPILE[_compile_context · 上下文组装]
        CALL_LLM[_call_llm · LLM调用]
        DIRECT[_direct_llm_call · fallback]
        SUBSYS[40+ 子系统 · Mind/Meta/ABC/OCEAN/...]
    end

    subgraph GATEWAY["Gateway (:8080)"]
        AUTH[鉴权 · api_keys]
        ROUTE[routingPool · 路由池]
        GEN[Generate · LLM调用]
        DEGRADE[gracefulDegradation · 降级]
        ADMIN[Admin · 厂商CRUD]
        PROBE[Prober · 30s健康探针]
    end

    CHAT --> V3
    GWPG --> GW_PROXY
    PROF --> V6
    TRACE --> V6
    ABC --> V6
    MIND --> V6
    META --> V6
    SET --> V6

    V3 --> V4
    V4 --> ON_EVENT
    ON_EVENT --> COMPILE
    ON_EVENT --> CALL_LLM
    ON_EVENT --> SUBSYS
    CALL_LLM --> DIRECT

    GW_PROXY --> GATEWAY
    CALL_LLM --> GATEWAY
    DIRECT --> GATEWAY

    GATEWAY --> DeepSeek
    GATEWAY --> OpenAI
    GATEWAY --> LMStudio
```

---

## 数据持久化

```mermaid
graph LR
    subgraph 持久化
        YAML[provider.yaml · 厂商配置 · 启动读]
        STATE[gateway.state.json · 用量统计 · 5min auto-save]
        SES_STOR[sessionStorage · 聊天消息 · 实时]
        LOCAL_STOR[localStorage · 表单数据 · 实时]
    end

    GWPG -->|保存Key| YAML
    GW -->|用量快照| STATE
    CHAT -->|消息| SES_STOR
    GWPG -->|表单| LOCAL_STOR
```

---

## 错误恢复

```mermaid
graph TD
    REQ[LLM请求] --> GW[Gateway]
    GW --> OK{成功?}
    OK -->|是| RESP[返回回复]
    OK -->|否| RETRYABLE{可重试?}
    RETRYABLE -->|是| NEXT[试下一个routingPool厂商]
    NEXT --> GW
    RETRYABLE -->|否| ERR[返回错误]
    NEXT --> EXHAUST{全部耗尽?}
    EXHAUST -->|是| ERR
```

---

## 当前状态

```
✅ Gateway: 9 providers, deepseek active+key, routingPool管理
✅ API: V3/V4/V6 全端点, GatewayLLMProvider
✅ Engine: on_event → compile_context → call_llm → fallback
✅ Chat: POST /v3/session/{id}/message → 回复
✅ 持久化: provider.yaml + localStorage + sessionStorage
✅ 降级: gracefulDegradation → routingPool 自动切换

⚠️  Message消失: zustand store已部署, 待前端构建验证
⚠️  上下文隔离: to_prompt预算过滤已修, 待API重启
```
