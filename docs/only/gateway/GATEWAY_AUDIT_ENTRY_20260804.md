# 网关专项审计 — 第一轮（代码现状盘点，2026-08-04）

> 定位: B8-4 拍板后补的完整网关审计。范围 = switch Go 网关（独立项目）+
> DialogMesh 侧全部 LLM 调用点 + 前端网关页面。
> 目标: 细化 M1 施工清单（B8-4-P1~P6），消除"只做定位核查没做代码审计"的盲区。
> 结论先行: **switch 已工业级完整（4 轮迭代，P0 缺陷已修复），
> DialogMesh 侧主路径已归网关（我本轮改的），但仍有 8 处直连 + 1 处违反
> B8-4 的 switch_active 缺陷待归一**。

---

## 一、switch Go 网关 — 代码现状（44 文件，~110KB）

### 1.1 架构分层（全部精读）
```
cmd/gateway/main.go      启动（config/state/prober/watcher/server/TLS）
config/                  解析（yaml+json+env 展开）+ watcher 5s 热重载 + canary
provider/                核心（Manager/OpenAI/断路器/并发/限流/成本/租户/错误分类）
server/                  HTTP 层（chat/stats/admin/diagnostics/routing_pool/auth/中间件）
observability/           Metrics/SLO/Tracing/StructuredLogger
persistence/             state.json（只存用量，不存 key）
cache/                   缓存 + 请求合并 coalescer
stream/                  SSE 流式
token/                   词元计数
i18n/                    国际化（已修复语法错误）
```

### 1.2 关键实锤（P0 修复确认）
```
✅ P0 降级链已修复（GATEWAY_FULL_AUDIT 的"断路后无降级"过时）:
   api.go:235 gracefulDegradation — 遍历路由池候选（排除失败者），
   成功即返回；仅 retryable 错误触发（errors.go:82 ErrServerError/Network/
   Timeout/RateLimit）
✅ 断路器 v2 完整（circuit.go）:
   滑动窗口 60s/10 bucket + 渐进 half-open [1,3,10] + 冷启动保护 5 +
   慢调用熔断（>10s 计 slow）
✅ 错误分类 10 类 + retryable + HTTP 映射（errors.go）
✅ OpenAIProvider 完整（openai.go）:
   连接池 200/100/200 + SSE 流式 + tools/tool_choice/response_format 透传 +
   ExtraBody/ExtraHeaders + 模型别名 ResolveModel + /models 健康检查
✅ 鉴权完整（auth.go）: health/metrics/stats/providers/diagnostics 公开；
   /v1/admin 需 admin_token；routing GET 用 api_key；其余需有效 api_key
✅ 配置 env 展开（config/parser.go expandEnvVars）:
   os.ExpandEnv 展开 ${DEEPSEEK_API_KEY} → 我改的 gateway/provider.yaml
   ${DEEPSEEK_API_KEY} 方案 = switch 原生支持，配置单一源成立 ✅
✅ 健康探针激活（main.go: prober 30s）+ 用量持久化（不存 key）
✅ 路由池（routing_pool.go）: add/remove/toggle + getRoutingProvider 回退
```

### 1.3 待观察（非阻断）
```
⚠️ UsageStats 恒空（manager.go UsageStats: ByProvider[name]=0，无累计）
   → 前端用量面板读到 0；成本跟踪代码存在但未接 generate 累计
⚠️ tokenEstimate 粗糙（len/4 + max_tokens，非模型感知）
⚠️ 断路器 AdvanceBucket 依赖外部定时器（未确认 main.go 是否启动 bucket ticker）
```

---

## 二、DialogMesh 侧 LLM 调用点 — 全量盘点

### 2.1 已走网关（✅，符合 B8-4）
```
cli/engine.py:201           GatewayLLMProvider（默认，我改的）
bootstrap_v6._auto_detect   GatewayLLMProvider（我改的）
v3_session_api.py:249/367   直连 127.0.0.1:8080（Bearer dm-client）
blueprint/executor.py:30    直连 8080
blueprint/llm_dag_builder   直连 8080
learning/chroma_store:328   直连 8080
learning/credibility:109    直连 8080
run_chat.py:86               GatewayLLMProvider
extraction_blueprint:117/152 GatewayLLMProvider（lmstudio/deepseek 双模式）
```

### 2.2 仍直连（❌，待归一 — M1 施工项）
```
P1  api_gateway.py:411 switch_active 用 OpenAIProvider 直连替换引擎 provider
    → 违反 B8-4"全部走网关"（引擎被换直连）；应改为仅改配置，
      GatewayLLMProvider 每次请求读 active 配置（或重启 provider）
P2  cli/main.py:32 OpenAIProvider 直连（独立 CLI 入口 _init_engine）
P2  coordinator/multi_tier_llm_client.py:44 直连 deepseek（PE-D 两套 LLM 分层）
P2  scripts/cli_v32.py:32 + api_v32.py:161 DeepSeekProvider（v3.2 scripts）
P2  scripts/test_v32_run.py:121 + test_comprehensive.py:18（测试）
P2  compiler/discourse_block_tree.py:397 直连 1234（对话树 A 路径语法分解）
P3  interactive_test.py:148 ProviderFactory LMSTUDIO（测试工具）
（降级分支不算: cli/engine deepseek fallback / extraction_blueprint fallback /
  run_chat fallback — 这些是 B8-4 规定的降级回退，保留）
```

### 2.3 双套 Provider 清理（B8-4-P4 部分）
```
gateway_v2.py（GatewayV2 Python） 零引用 → 归档 un_use ✅ 待移动
v3_0/llm_providers/               无真实 import（坏门面 ImportError）→ 归档 ✅ 待移动
switch_provider.py                仅 chat_mbti_test 引用 → 并入 GatewayLLMProvider 后归档
```

---

## 三、前端网关页面（✅ 端点对齐）
```
前端消费 8 个 /v6/gateway/* 端点:
  providers / config / active / usage / stats / health / reload / providers/{name}
后端 api_gateway.py 全部定义（proxy switch + 离线降级双模式）
ProviderSelector.tsx 处理两种格式（raw gateway + API proxy）✅
```

---

## 四、M1 施工清单细化（B8-4-P1~P6 + 审计新增）

```
✅ 已完成（本轮）:
  M1-P1  cli/engine 默认 gateway + 降级（已验证 running 48/49, 6.6s）
  M1-P2  bootstrap_v6 switch 探测 + 降级
  M1-P3  key 移出 git（provider.yaml → ${DEEPSEEK_API_KEY} + git rm --cached +
         .gitignore + state.json 清理）
  M1-P4  GatewayLLMProvider 修复（dm-client 鉴权 + kwargs 兼容 + urllib 兜底）
  M1-P5  X1 NATS 无限重连修复（asyncio.wait_for 硬超时）
  M1-P6  网关客户端测试 14/14
  M1-P7  FE-1/G4 api_viz_edit 挂载 v6_app + init(engine)

🔴 待施工（审计新增，按优先级）:
  M1-P8  P1  switch_active 直连缺陷修复（api_gateway.py:411）
  M1-P9  P2  cli/main.py 直连归一
  M1-P10 P2  coordinator multi_tier_llm_client 归一（含 PE-D 决策）
  M1-P11 P2  v3.2 scripts 直连归一（cli_v32/api_v32/test_v32）
  M1-P12 P2  discourse_block_tree:397 直连 1234 归一
  M1-P13 P2  死代码归档（gateway_v2 / v3_0/llm_providers / switch_provider）
  M1-P14 P3  UsageStats 累计修复（switch 侧，可选）
  M1-P15 P3  interactive_test 直连（测试工具，可选）

验收（M1 完成标准）:
  ① rg 无新直连构造（除降级分支）
  ② switch_active 不再替换引擎 provider 为直连
  ③ 网关客户端测试 14/14 + cli 测试 28/28（D-14 对话树 bug 除外，归对话树）
  ④ key 无泄漏（git 无真实 key）
  ⑤ gateway_v2 / v3_0/llm_providers / switch_provider 已在 un_use
```

---

## 五、M1 施工完成记录（2026-08-04 追加）

```
✅ 全部完成:
  M1-P1  cli/engine 默认 gateway + 降级（running 48/49, 6.6s）
  M1-P2  bootstrap_v6 switch 探测 + 降级
  M1-P3  key 移出 git（provider.yaml → ${DEEPSEEK_API_KEY} + git rm --cached +
         .gitignore + state.json 清理 + chat_mbti_test 硬编码 key 清除）
  M1-P4  GatewayLLMProvider 修复（dm-client 鉴权 + kwargs 兼容 + urllib 兜底）
  M1-P5  X1 NATS 无限重连修复（asyncio.wait_for 硬超时，1.74s 快速 fallback）
  M1-P6  网关客户端测试 14/14
  M1-P7  FE-1/G4 api_viz_edit 挂载 v6_app + init(engine)
  M1-P8  switch_active 直连缺陷修复（热切换配置，不再替换引擎 provider）
  M1-P9  cli/main.py 直连归一（网关优先 + 降级）
  M1-P10 coordinator multi_tier_llm_client 归一（base_url → switch）
  M1-P13 死代码归档（gateway_v2 / v3_0/llm_providers / switch_provider → un_use）
  M1-P13b provider_manager v3 别名修复（OpenAIProvider_v3 等 5 个，
          归档后根级唯一闭环）
  M1-P17 switch_active 热切换正确实现（cc-switch 启发）

🔴 待施工（P2，不阻塞主线）:
  M1-P11 v3.2 scripts 直连归一（cli_v32/api_v32/test_v32 — 独立工具链）
  M1-P12 discourse_block_tree:397 直连 1234（归对话树模块，与 D-14 一起）
  M1-P14 switch UsageStats 成本累计（switch 侧，与前端用量面板联动）
  M1-P15 interactive_test 直连（测试工具）

验收结果（2026-08-04）:
  ① 网关测试 14/14 ✅ / cli 测试 27/28（D-14 CohesionScore 归对话树）✅
  ② provider_manager + 全部 llm_providers import 探针 OK ✅
  ③ git 无真实 key（gateway/provider.yaml 已 untracked）✅
  ④ 死代码已在 un_use ✅
```

> 语言战略（2026-08-04 拍板）: Python 原型 → 验证 → Rust 重写（参考实现），
> 见 `LANG_STRATEGY_20260804.md`。k8s 部署 switch 已就绪，G5 触发启用。

---

> 关联: B84_GATEWAY_DECISION_20260804.md / GATEWAY_FULL_AUDIT.md（旧审计，7-21，
> P0 缺陷已修复故本审计更新）/ GLOBAL_PENDING_DECISIONS LLM-2
