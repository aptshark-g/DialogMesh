# B8-4 网关 vs 进程内 Provider — 拍板定案（2026-08-04）

> 定位: 真决策 B8-4（归 LLM-2，含 I1-8 双套 Provider）正式定案。
> 关联: `GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md` 聚类 7 B8-4 + 聚类 8 I1-8；
> `GLOBAL_PENDING_DECISIONS_20260803.md` LLM-2。
> 修正过程: 首轮建议"进程内为主、网关可选"→ 用户指出 switch 是专门嵌入式网关项目
> → 核查后修正为"网关主路径 + 进程内降级回退"（本文件为最终版）。

---

## 一、核查事实（代码级实锤）

### 1.1 switch 是既定架构（不是选项）
```
C:\Users\APTShark\PycharmProjects\switch = 独立 Go 网关项目
  go.mod: github.com/aptshark/gateway | main 分支 | 20+ 提交 | 4 轮工业级迭代
  能力: 滑动窗口断路器 / Gradient2 自适应并发 / 加权路由 / 请求合并 /
        SLO 燃烧率 / 多租户成本 / 热重载 / 诊断端点
  docs/BINDING_DIALOGMESH.md v1.0 (2026-07-19):
    "DialogMesh 不再直连 LLM Provider——全部通过 switch gateway 代理"
    "DialogMesh 只认 switch 的地址和端口——不知道上游有哪些 Provider"
    "switch 的 provider.yaml 是唯一 Provider 配置源"
    "DialogMesh Python Gateway API 变成 switch 的管理前端"
```

### 1.2 绑定落地现状（部分落地，主路径不一致）
```
✅ 已落地:
  - scripts/start.py 一键启动（自动探测 → 启动 gateway.exe → health check → 回退）
  - api_gateway.py /v6/gateway/* = 代理 switch（离线降级 builtin 双模式）
  - v3_session_api.py LLM 调用直连 127.0.0.1:8080（Bearer dm-client）
❌ 不一致:
  - cli/engine.py start_engine 默认 provider_type="deepseek"（直连 OpenAIProvider）
  - bootstrap_v6._auto_detect_llm → DeepSeekProvider 直连
  → 主路径仍是直连，与绑定设计"全部走网关"相悖
```

### 1.3 双套 Provider 真面目（I1-8）
```
根级 core/agent/llm_providers/（14 文件）= 唯一活实现
  OpenAIProvider/LocalProvider/MockProvider/Failover/HybridRouter/
  ProviderManager/CircuitBreaker/Streaming 全在此
v3_0/llm_providers/（base 19.8KB + failover + hybrid + local + mock + openai）
  = 死代码 + 坏门面: __init__ 想从根级 re-export，实测 ImportError:
    cannot import name 'LLMConnectionError' from 'core.agent.llm_providers.base'
  全库零引用（rg 仅 docstring 提及）
```

### 1.4 网关侧三套并存（两套死/半死）
```
GatewayLLMProvider (gateway_provider.py)  = 唯一被真实消费的网关客户端
  （cli/engine.py gateway 模式 / run_chat.py / extraction_blueprint.py）
switch_provider.py (SwitchGatewayProvider) = 仅 v4 测试用
GatewayV2 (core/agent/gateway/gateway_v2.py 15KB pingora 管线)
  = 零引用死代码（能力与 ProviderManager 重叠）
api_gateway.py (/v6/gateway/*) = 活（switch 代理 + 离线降级）
```

### 1.5 安全项
```
DialogMesh 仓库 gateway/provider.yaml 带真实 DeepSeek key（sk-20d7...）
  且已被 git 跟踪（git ls-files gateway/provider.yaml ✅）
switch 仓库 provider.yaml key 全空
→ 两文件不同源，key 已入库 = 必须处理
```

### 1.6 运行状态
```
switch 当前未运行（8080 无响应）
```

---

## 二、拍板内容（正式）

```
B8-4: 网关主路径 + 进程内 Provider 降级回退

① 主路径归一（P0）:
   cli/engine.py start_engine 默认 provider_type="gateway"
   bootstrap_v6._auto_detect_llm → switch（不再直连 DeepSeek）
   v3_session_api 已有 switch 调用 ✅ 保留
   → "全部 LLM 调用走 switch" = BINDING_DIALOGMESH v1.0 落地

② 降级回退（switch 离线时）:
   保留 OpenAIProvider/LocalProvider/MockProvider 为 fallback
   （api_gateway 已实现离线降级，引擎侧同样处理）
   不建第二套路由内核——ProviderManager 定位为 fallback 提供者集合，
   主路由 = switch

③ 配置单一源（P0 安全）:
   switch/provider.yaml = 唯一配置源
   DialogMesh 仓库 gateway/provider.yaml 改为从 switch 同步
   （或仅保留 provider.example.yaml）
   真实 key 移出 git → 环境变量 / 本地未跟踪文件

④ 死代码清理（P1）:
   GatewayV2 (gateway_v2.py)    → 归档 un_use（正式网关是 switch）
   v3_0/llm_providers/          → 归档 un_use（坏门面 + 死代码）
   switch_provider.py           → 并入 GatewayLLMProvider
   双套 Provider 归一 = 根级为唯一实现

⑤ 测试走网关:
   集成测试走 switch（可 mock switch 或起真实 gateway.exe）
   mock provider 仅用于离线单测
```

---

## 三、与 B4-5 的关系（同构）

```
B4-5: 内核唯一（dispatch 函数集）+ 传输可插拔（CLI/REST/MCP/WS）
B8-4: 内核唯一（switch 网关协议）+ 传输可降级（进程内 Provider = fallback）
→ 两个都是"唯一内核 + 传输按需"，非平行替代
```

---

## 四、施工前置（定案落地时用）

```
B8-4-P1  cli/engine.py start_engine 默认 provider_type="gateway"（含状态迁移）P0
B8-4-P2  bootstrap_v6._auto_detect_llm 改为 switch 探测 + 降级 P0
B8-4-P3  key 移出 git + 配置单一源（switch/provider.yaml）P0
B8-4-P4  GatewayV2 / v3_0/llm_providers / switch_provider 清理归档 P1
B8-4-P5  引擎侧离线降级回退（switch 不可用 → fallback provider）P1
B8-4-P6  集成测试走网关（mock switch + 真实 gateway 双模式）P1
```

## 五、验收标准

```
① start_engine 默认启动即走 switch（无 provider_type 显式指定时）
② bootstrap_v6 启动后 LLM 调用全部经 8080（rg 无新直连构造）
③ git 中无真实 key（gateway/provider.yaml 只剩 example 或空模板）
④ GatewayV2 / v3_0/llm_providers 已在 un_use，根级 llm_providers 为唯一实现
⑤ switch 离线时引擎可降级到 fallback provider，不崩
⑥ 集成测试覆盖 走网关 + mock switch 两种模式
```

---

> 状态: ✅ 已拍板（2026-08-04）｜ 施工前置 6 项（P0×3, P1×3）｜
> 下一项: B1-8 CognitiveWorkspace 容器（归 LLM-1）
