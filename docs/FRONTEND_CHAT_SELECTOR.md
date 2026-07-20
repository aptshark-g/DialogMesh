# DialogMesh v6 — 对话模型选择业务流

> 用户通过前端选择 LLM 厂商 → 发送时指定模型 → 网关加权路由 → 可见切换

---

## 完整流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant CH as ChatPage
    participant SEL as ProviderSelector
    participant API as API(:8000)
    participant GW as Gateway(:8080)
    participant LLM as 上游 LLM

    Note over CH,SEL: 页面加载
    CH->>API: GET /v6/gateway/providers
    API->>GW: GET /v1/providers
    GW-->>API: [{ deepseek:active, lmstudio:active, openai:inactive ...}]
    API-->>CH: 9 providers
    CH->>SEL: 填充下拉菜单 (只显示 active=true 的)

    Note over U,SEL: 用户选择厂商
    U->>SEL: 下拉选 "DeepSeek v4 Flash"
    SEL->>API: PUT /v6/gateway/active { provider: "deepseek", model: "deepseek-v4-flash" }
    API->>GW: PUT /v1/admin/providers/deepseek { active: true }
    GW-->>API: OK
    API-->>SEL: { switched: "deepseek", healthy: true }

    Note over U,LLM: 发送消息
    U->>CH: 输入 + 发送
    CH->>API: POST /v3/session/{id}/message { content, provider?, model? }
    API->>GW: POST /v1/chat/completions { model:"deepseek-v4-flash" }
    GW->>GW: 加权路由: DeepSeek(80%) vs OpenRouter(20%)
    GW->>LLM: → DeepSeek API
    LLM-->>GW: AI 回复
    GW-->>API: 200 { choices: [...] }
    API-->>CH: { content: "..." }
    CH->>U: 显示回复 + 脚注 "via DeepSeek · 152ms"

    Note over GW,LLM: 故障切换
    GW->>GW: DeepSeek 返回 503 → 断路器 OPEN
    GW->>GW: 降级到 OpenRouter
    GW->>LLM: → OpenRouter API
    LLM-->>GW: AI 回复
    GW-->>API: 200 { choices: [...] }
    API-->>CH: { content: "...", switched: true }
    CH->>U: 显示 "⚠️ 已从 DeepSeek 切换到 OpenRouter"
```

---

## ProviderSelector 组件交互

```mermaid
flowchart TD
    A["ProviderSelector 挂载"] --> B["GET /v6/gateway/providers"]
    B --> C["过滤: active=true"]
    C --> D["渲染下拉菜单"]

    D --> E{"用户点击"}
    E -->|"选厂商+模型"| F["PUT /v6/gateway/active"]
    F --> G["更新 ChatPage state: activeProvider"]
    G --> H["发送消息时附加 provider 参数"]
    
    E -->|"查看详情"| I["展开面板: 显示电路状态/延迟/健康分"]

    H --> J["API → Gateway → 加权路由"]
    J --> K{"响应是否故障切换?"}
    K -->|"是"| L["前端 Toast: '已从 A 切换到 B'"]
    K -->|"否"| M["正常返回"]
```

---

## 实现清单

| 功能 | 文件 | 状态 |
|------|------|:---:|
| Provider 下拉选择器 | ChatPanel.tsx (新增) | ❌ 未实现 |
| 当前 Provider 显示 | ChatPanel header | ❌ 未实现 |
| 发送时带 model 参数 | ChatPage.tsx handleUserMessage | ❌ 未实现 |
| 切换 Provider API | v6.ts setGatewayActive | ✅ 已有 |
| 加权路由 | Gateway routing.go | ✅ 已有 |
| 断路器+降级 | Gateway circuit.go | ✅ 已有 |
| 故障切换提示 | ChatPage 响应解析 | ❌ 未实现 |
