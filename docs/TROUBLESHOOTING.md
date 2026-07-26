# DialogMesh 已知问题与解决方案

> 2026-07-25 · 重复出现的问题记录

---

## 1. 端口占用 (重复 4+ 次)

### 现象
```
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)
[WARN] Port 8080 already in use
```

### 根因
- 旧进程未正确关闭 → 端口仍被占用
- Windows 默认 TIME_WAIT=120s
- 多次启动脚本叠加

### 解决
1. `SO_REUSEADDR` — start_server.py 已加 (2026-07-25)
2. 启动前 `_check_port()` → 占用时提示而非报错
3. Gateway: 必须在 `gateway/` 目录运行 (provider.yaml 位置)

### 快速清理
```bash
# Windows
netstat -ano | findstr :8000    # 找到 PID
netstat -ano | findstr :8080    # 找到 PID
taskkill //PID <pid> //F

# Linux/Mac
lsof -i :8000 | grep LISTEN
kill -9 <pid>
```

---

## 2. Gateway: provider.yaml not found

### 现象
```
gateway: config: read provider.yaml: The system cannot find the file specified.
```

### 根因
`gateway.exe` 在当前工作目录查找 `provider.yaml`

### 解决
必须从 `gateway/` 目录或绝对路径运行：
```bash
cd gateway && ./gateway.exe
# 或
./gateway/gateway.exe  # 需要 gateway/ 下的 provider.yaml
```
start_server.py 已设置 cwd=gateway/ (2026-07-25)

---

## 3. ModuleNotFoundError: core.agent.v3_2.integration

### 现象
```
AgentPipeline lazy import failed: No module named 'core.agent.v3_2.integration'
```

### 根因
v3_2 遗留模块未移植到 v6，lazy import 失败

### 影响
仅警告，不影响功能。优雅降级已处理。

---

## 4. 模块导入链过重 (超时)

### 现象
```
[Command timed out after 5s]
```

### 根因
import chain: agent_native → UnifiedContext → DiscourseManager → v3 重依赖

### 解决
v6_app.py 绕过重依赖，独立入口。start_server.py 已切到 v6_app。

---

## 5. pydantic_core 损坏 (hermes venv)

### 现象
```
ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
```

### 影响
仅影响 hermes venv 的 python，不影响项目编译。项目用 conda python。

### 解决
```bash
pip install --force-reinstall pydantic pydantic-core
```

---

## 6. start.bat 跳过重启, 新代码未生效

### 现象
前端正常轮询 → 全部返回旧数据或 404 → 聊天发不出

### 根因
start.bat 检测端口占用 → 跳过 API 启动 → 旧服务器仍在运行旧代码

### 解决
start.bat 现在自动杀旧进程再重启 (2026-07-26 修复)
或者手动: Ctrl+C 关闭旧 API 窗口 → 重新运行 start.bat

---

## 7. 前端崩盘 — stub ↔ TS 类型不一致 (重复 6+ 轮, 2026-07-26)

### 现象
```
TypeError: t.map is not a function                              (DashboardPage)
TypeError: Cannot convert undefined or null to object           (CognitiveProfilePage)
TypeError: Cannot read properties of undefined (reading 'total_patterns')  (BehaviorPage)
TypeError: Cannot read properties of undefined (reading 'map')            (GatewayPage)
TypeError: Cannot read properties of undefined (reading 'toLocaleString') (GatewayPage)
TypeError: Cannot read properties of undefined (reading 'length')         (MetaCenterPage)
HTTP 404: {"detail":"Not Found"}                              (多个页面)
```

### 三类根因

#### A. "多包一层" — wrapper 层多余
Python stub 返回 `{"config": {"failover_chain": [], ...}}` 但 TS 类型是**平铺对象**：
```ts
export interface V6GatewayConfig {
  active_provider: string;    // ← 顶层字段!
  failover_chain: string[];   // ← 顶层字段!
  stats: Record<...>;         // ← 顶层字段!
}
```
→ component 读 `config.failover_chain` 时 `config` 是 `{"config": {...}}`，`.failover_chain` = `undefined` → `.map()` crash。

**所有 Gateway 类型都是平铺的**：V6GatewayConfig、V6GatewayUsage、V6GatewayStats、V6GatewayHealth 均无外层 wrapper。

#### B. "字段嵌套层级不对" — 不是少字段，是放到错误层级
Component 访问 `patterns.stats.total_patterns`，stub 返回 `{"total_patterns": 0}` → `patterns.stats` = `undefined`。
Component 访问 `versions.commits.length`，stub 返回 `{"versions": []}` → `versions.commits` = `undefined`。

#### C. "缺失端点" — 404
前端调用了 `getBelief()`、`getSubgraph()`、`getAnnotations()`、`getProfileCorrections()` 但后端根本没有这些路由。

### 根因 — AI Agent 方法论缺陷

6 轮反复的根本原因不是缺信息，而是**工作流程缺失了一步交叉校验**：

```
❌ 错误流程:
  1. 读前端 API 函数签名 → getGatewayConfig(): Promise<V6GatewayConfig>
  2. 凭直觉写 Python stub → {"config": {"failover_chain": []}}   ← 猜的!
  3. 没对比 step 2 产物 vs TS 类型定义
  4. 前端爆炸 → 重试 → 还是猜 → 再炸

✅ 正确流程:
  1. 读前端 API 函数签名 → 拿到返回类型名
  2. grep src/types/api.ts 拿完整的 interface 定义
  3. 逐字段生成 Python dict，字段名和层级严格匹配
  4. 如果页面组件的 `?.` 访问链和 TS 类型不一致 → 以组件实际访问为准
```

### 方法 — 一次定位所有问题的脚本

```bash
# 1. 扫所有页面的 ?. 危险访问 (找出所有可能 crash 的 .map/.length/.toLocaleString)
cd frontend && grep -rn "\.map\|\.length\|\.toLocaleString" src/pages/ | grep -v "//"

# 2. 回溯到 API 调用 → 找到端点 → 对比 TS 类型 vs stub 字段
grep -A 10 "export interface V6XxxResponse" src/types/api.ts

# 3. 确认没有 "多包一层" — 看 getXxx() 的返回类型是否直接就是 V6Type
grep "export function getGateway" src/api/v6.ts
# getGatewayConfig(): Promise<V6GatewayConfig>   ← 直接返回 V6GatewayConfig，不包装!
```

### 经验
```
错误模式: 前端 GET /v6/xxx 200 → resp.json() → component 解构失败 → ErrorBoundary
规律:
  - "*.map is not a function"  → 后端返回了对象但预期是数组 / 字段嵌套层级错
  - "Cannot read * of undefined" → 后端返回了对象但字段名不对 / 多包一层
  - "*.toLocaleString" / "*.length" → 同上，数值/数组字段缺失
  - 404 → 端点不存在
→ 读到 TS interface → diff stub → 修
```

### 42 端点完整对标表 (最终版, 2026-07-26)
```
端点                 TS 返回类型                     stub 格式                                注意
/profile            V6ProfileResponse              {oceAN_dims, mbti, turn_count, ...}       ← 平铺!
/trace              V6TraceResponse                {reason_distribution, avg_confidence, total}
/abc                V6AbcResponse                  {}   (Record)
/mind               V6MindResponse                 {}   (Record)
/mind/full          自定义                          {dimensions, raw, projections}
/graph              V6GraphResponse                {nodes, edges, subgraph_nodes}
/discourse-tree     V6DiscourseTreeResponse        {blocks, total}
/objects            V6ObjectsResponse              {nodes, edges, total_objects}
/rules              V6RulesResponse                {rules, total}
/relations          V6RelationsResponse            {}   (Record)
/causal             V6CausalResponse               {}   (Record)
/behavior           V6BehaviorResponse             {}   (Record)
/behavior/patterns  自定义                          {stats: {total_patterns, user_approved}}  ← stats 嵌套!
/behavior/predict   V6BehaviorPredictResponse      {recent_actions, predictions}
/inertia            自定义                          {total_patterns, stable, confirmed, breaking, constraints}
/engineering        V6EngineeringResponse          {}   (Record)
/engineering/modules  自定义                        {modules, count}
/pipeline           V6PipelineResponse             {}   (Record)
/extraction         V6ExtractionResponse           {}   (Record)
/perspectives       V6PerspectivesResponse         {}   (Record)
/parameters         自定义                          {}   (Record)
/context            自定义                          {}   (Record)
/subgraph           自定义                          {}   (Record)
/subgraph/cache     自定义                          {hit_rate, total_queries}
/subgraph/{p}       V6SubgraphResponse             {perspective, domains, entries, total_tokens, budget}  ← 路径参数!
/belief             V6BeliefResponse               {total_hypotheses, locked, avg_evidence, by_hypothesis}
/persistence        V6PersistenceResponse          {annotation_store, unified_store, oceAN_saved, rules_saved}
/persistence/graphs V6SessionListItem[]            []   ← 裸数组!
/sessions           V6SessionListItem[]            []   ← 裸数组!
/providers          V6ProvidersResponse            {active, failover}
/providers/tokens   V6TokensResponse               {current, all_sessions}
/router/modes       V6RouterModesResponse          {available, modes, active, force_mode, disabled}
/metrics            V6MetricsResponse              {}   (Record)
/annotate           V6AnnotationsResponse          {annotations, total}
/annotate/stats     V6AnnotationStatsResponse      {total, by_author, by_date}
/profile/corrections V6ProfileCorrectionsResponse   {corrections, total}
/degradation        自定义                          {level, score}
/ttl                自定义                          {ttl_stats, total}
/recursive-map      自定义                          {map, count}
/meta/stats         自定义                          {stats: {decisions_total, pending, queue_size, reviewed}, self_audit}
/meta/queue         自定义                          {queue, pending}
/versions/profile   自定义                          {commits, target, current}                 ← commits 数组!
/gateway/providers  V6GatewayProvidersResponse     {providers, active_provider, active_model}  ← 平铺!
/gateway/config     V6GatewayConfig                {active_provider, active_model, failover_chain, auto_failover, max_retries, timeout_ms, stats}  ← 平铺!
/gateway/usage      V6GatewayUsage                 {current_session: {...}, all_sessions: {...}}  ← 平铺!
/gateway/stats      V6GatewayStats                 {requests, tokens, latency_p50/95/99, cache_hit_rate, errors_by_provider, requests_by_model}  ← 平铺!
/gateway/health     V6GatewayHealth                {status, providers_total, providers_healthy, circuits}  ← 平铺!
```

### 教训总结
```
1. TS interface 的层级 = stub dict 的层级 — 不要自己加/减包装层
2. component 的 ?. 访问链 > TS type 定义 — 如果两者不一致，以 component 为准
3. 裸数组 ≠ {key: []} — getSessions(): Promise<Foo[]> 必须 return []
4. 读 TS 源码 > 猜 — grep src/types/api.ts 永远比凭直觉快
5. 改 stub 后必须重启后端 — curl 验证 > 凭 git commit 假设生效
```
