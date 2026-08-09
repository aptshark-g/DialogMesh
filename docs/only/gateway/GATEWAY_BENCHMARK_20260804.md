# 网关横向对标审计 — 业界成熟网关对比（2026-08-04）

> 定位: 网关审计第二轮（外部视野）。补充第一轮"内部完整性审计"的盲区——
> switch 相比业界成熟 LLM 网关的能力差距。
> 对标对象: LiteLLM / Portkey / one-api / cc-switch / Higress（2026-08-04 实测 GitHub 数据）。
> 结论先行: **switch 核心能力（断路器/降级/路由/鉴权/流式）已与业界对齐，
> 缺的是 3 类外围能力（虚拟 key/多租户、成本累计、管理 UX）——都不阻塞
> DialogMesh 单用户主路径，按 G5 分布式触发再补**。

---

## 一、对标对象（实测数据 2026-08-04）

```
LiteLLM    (BerriAI)    55.5K★  Python+Rust core | AI Gateway, 100+ LLM,
                         虚拟 key/成本/guardrails/负载均衡/admin dashboard
Portkey    (Portkey-AI) 12.6K★  TypeScript | 1600+ 模型, <1ms, 122KB,
                         自动重试/fallback/条件路由/guardrails/MCP Gateway
one-api    (songquanpeng) 36.2K★ Go 单二进制 | 25+ 国内模型渠道,
                         渠道管理/令牌管理/负载均衡/stream/Docker 一键
cc-switch  (farion1231) 124K★ Rust+Tauri 桌面 | 8 工具 provider 切换器
                         （Claude Code/Codex/Hermes/OpenClaw...），
                         50+ 预设, 本地代理热切换, MCP/提示词/skills 管理,
                         用量仪表盘, 云同步/DeepLink
Higress    (higress-group) 9K★ Go | AI Native API Gateway（企业级）
```

---

## 二、能力矩阵（switch vs 业界）

| 能力 | switch | LiteLLM | Portkey | one-api | cc-switch | 备注 |
|---|:---:|:---:|:---:|:---:|:---:|---|
| OpenAI 兼容统一 API | ✅ | ✅ | ✅ | ✅ | ✅(代理) | 核心协议 |
| 多 Provider 路由 | ✅ | ✅ 100+ | ✅ 1600+ | ✅ 25+ | ✅ 8 工具 | switch 少但够 |
| 断路器 | ✅ 滑动窗 v2 | ✅ | ✅ | — | ✅ | switch 完整 |
| 自动降级/fallback | ✅ gracefulDegradation | ✅ | ✅ | ✅ | ✅ | 已对齐 |
| 流式 SSE | ✅ | ✅ | ✅ | ✅ | — | switch ✅ |
| 请求合并 coalescing | ✅ cache/coalescer | — | — | — | — | switch 领先 |
| 缓存 | ✅ 5min TTL | ✅ | ✅ | — | — | — |
| 鉴权 (api_key/admin) | ✅ | ✅ 虚拟key | ✅ | ✅ 令牌 | — | switch admin 分离 |
| **虚拟 key / 多租户** | ❌ 单租户 | ✅ | ✅ | ✅ 渠道+令牌 | — | **switch 缺口 1** |
| **成本累计/用量** | ⚠️ UsageStats 恒空 | ✅ | ✅ | ✅ | ✅ 仪表盘 | **switch 缺口 2** |
| 健康探针 | ✅ 30s Prober | ✅ | ✅ | — | ✅ | — |
| 热重载 | ✅ 5s watcher | ✅ | ✅ | — | ✅ | — |
| 管理 UI | ⚠️ gtui 雏形 | ✅ dashboard | ✅ | ✅ 完整 | ✅ 完整 | **switch 缺口 3** |
| MCP 集成 | ❌ | — | ✅ MCP Gateway | — | ✅ MCP 面板 | 与 B8-8 相关 |
| 多模型渠道预设 | ⚠️ 9 个 | ✅ 100+ | ✅ 1600+ | ✅ 25+ 国内 | ✅ 50+ | 规模差 |
| 部署形态 | 单二进制 | Docker/PyPI | 云/Docker | 单二进制 | 桌面 app | — |

---

## 三、关键洞察（对标后）

### 3.1 switch 已对齐的核心（第一轮审计确认）
```
断路器 v2 / 降级链 / 错误分类 / 流式 / 缓存+合并 / 鉴权分离 /
健康探针 / 热重载 / 路由池 — 全部工业级，与 LiteLLM/Portkey 同级
```

### 3.2 三个缺口（都不阻塞单用户主路径）
```
缺口1 虚拟 key / 多租户（LiteLLM/one-api 有）
  → DialogMesh 单用户不需要；多 agent/多客户端时（G5 触发）再补
  → switch 已有 auth 多 key 基础（api_keys 数组），扩展成本低

缺口2 成本累计恒空（manager.go UsageStats）
  → 第一轮审计已发现；修复 = 在 Generate 成功路径累计 prompt/completion
  → 单用户价值：用量面板真实化（前端 /v6/gateway/usage 依赖）

缺口3 管理 UX（gtui 雏形 vs one-api 完整控制台）
  → DialogMesh 已有前端 GatewayPage + api_gateway 双模式，够用
  → 完整控制台 = 阶段 2（与 G5 同触发）
```

### 3.3 cc-switch 的独特启发（对 DialogMesh 价值最大）
```
cc-switch 不是请求代理，是"配置管理 + 切换 UX"——与 switch 互补:
  ✅ 通用 provider 配置同步到多个工具（Claude Code/Codex/Hermes...）
     → 我们的 Hermes/Codex/OpenClaw 协同可借鉴（B2-3 多 agent）
  ✅ 本地代理热切换（无需重启）——Claude Code 支持 provider 热切换
     → 我们的 switch_active（api_gateway.py:411）正是要做这个，
       目前用 OpenAIProvider 直连替换 = 错误实现（M1-P8 要修）
  ✅ 50+ 预设 + 一键导入/导出 + 云同步/DeepLink
     → 我们的 provider.example.yaml 只有 9 个预设，可扩
  ✅ MCP 面板统一管理（Claude/Codex/Gemini 的 MCP servers）
     → 与 B8-8（MCP 边界）联动
  ✅ 用量仪表盘 + 每模型自定义定价
     → 对应我们的缺口 2（成本累计）
  ⚠️ cc-switch 本身是桌面配置器，不做 LLM 请求代理的完整工业能力
     （断路器/降级/错误分类/连接池）→ 我们的 switch 恰好补这个
  → 结论: switch（代理内核）+ cc-switch 式管理 UX = 完整形态
```

---

## 四、对标后的 M1 施工修订

```
原 M1 清单（内部审计）:
  M1-P1~P7 ✅ 已完成 / M1-P8~P15 待施工（见 GATEWAY_AUDIT_ENTRY）

对标新增（纳入 M1）:
  M1-P16 成本累计修复（switch UsageStats — Generate 成功路径累计）P2
          → 前端用量面板真实化（缺口 2，单用户有价值）
  M1-P17 switch_active 正确实现（热切换 = 改网关 active 配置，
          不是替换引擎 provider）— 强化 M1-P8，参考 cc-switch 热切换 P1
  M1-P18 多 key 基础利用（auth api_keys 数组 → 预留多客户端，不施工）P3

明确不做的（对标排除）:
  ✗ 虚拟 key/多租户（G5 触发）
  ✗ 完整管理控制台（G5 触发）
  ✗ 100+ 模型渠道预设（按需扩 provider.yaml，不一次铺）
  ✗ MCP Gateway（归 B8-8 mcp 施工）
```

---

## 五、结论

```
① switch 核心 = 业界同级（第一轮内部审计 + 本轮横向对标双确认）
② 三个缺口均不阻塞单用户主路径，按 G5 分布式触发补
③ cc-switch 的"配置管理 + 热切换 UX"是 switch 缺的互补面，
   启发 M1-P17（switch_active 正确实现）——本轮最有价值的对标输入
④ M1 施工 = 内部清单（P8-P15）+ 对标新增（P16-P17），P18 预留
```

---

> 数据来源: GitHub API 实测（2026-08-04）: BerriAI/litellm 55463★ /
> Portkey-AI/gateway 12636★ / songquanpeng/one-api 36168★ /
> farion1231/cc-switch 124028★ / higress-group/higress 9018★
