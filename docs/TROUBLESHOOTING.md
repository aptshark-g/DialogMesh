# DialogMesh 已知问题与解决方案

> 2026-07-25 · 重复出现的问题记录

---

## 状态核查（2026-08-06）— 本文档与当前代码的对应

> 核查方法: 源码逐条对照（stubs_api / api_gateway / GatewayPage / FlowchartCanvas）。

### 已解决（M1-M9 施工后）

| 条目 | 原问题 | 现状（实测） |
|---|---|---|
| §7 C 类缺失端点 | getBelief/getSubgraph/getAnnotations/getProfileCorrections 404 | ✅ 全部注册内核 dispatch: stubs_api.py L217-317（/subgraph /subgraph/cache /belief /profile/corrections /annotations） |
| §8a stub 覆盖真实网关 | stub 空数组遮蔽 switch 代理 | ✅ 已消除: stubs_api.py 第 4 行注释"Gateway 路由由 api_gateway.py 处理", 网关端点统一走 api_gateway.py 代理 switch |
| §8b 测试连接 0ms | 只读缓存不实测 | ✅ api_gateway 真 HTTP GET base_url 计时 |
| §8c ProviderCard 抖动 | memo 定义在组件体内 | ✅ 已移文件顶层（GatewayPage.tsx L65） |
| §10 ReactFlow 鼠标失效 | 环境层阻断（旧结论） | ✅ ConversationGraph（ReactFlow）交互已修复（2026-08-07 复核: 真根因 = 429 限流 + fitView minZoom 钳制, 见 §10f）; 任务画布 FlowchartCanvas（纯 SVG）在用 |

### 仍然适用（方法论, 已系统化）

- §7 方法论（读 TS interface → diff 后端 → 以组件 `?.` 访问链为准）已落地为
  `docs/only/frontend/FE_CONTRACT_REGISTRY_20260806.md`（全量格式登记 + 端点矩阵）。
- §7 教训 5（改后必须重启后端 + curl 验证）→ B5 绑定 smoke 的必做步骤。

### 新增问题（2026-08-06 用户报告, 与 §7 同源不同层）— ✅ 已施工

- **状态生命周期缺失（内存态 vs 持久化）**: LLM 规划任务图 → 后端直接落盘
  `task_graphs/{sid}.json`（原 v3_session_api.py:399-407, 保护=文件存在性非版本号）;
  前端编辑 PUT 无条件覆盖; 无内存态工作区 + 无版本冲突检测 → 竞态下前端操作
  被刷新/新规划吞掉。
- **2026-08-06 已修复（阶段 B P0）**: `TASK_GRAPH_VERSIONING_IMPL_20260806.md` —
  内存态工作区 + version + 409 冲突检测 + 前端乐观更新（冲突提示条:
  覆盖服务端/放弃本地）。后端 8/8 新测试 + 86/86 api 回归 + tsc/build 绿。
- **2026-08-06 同型已推广（B1）**: 图谱编辑 /v6/edit/* 全部版本化
  （engine._viz_version + 409 + 前端冲突条）, 记录 `B1_B6_IMPL_20260806.md`。

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

---

## 8. 网关 Provider 管理 (2026-07-26)

### 8a. 注册 Provider 无效 — stub shaow 真实路由器

#### 现象
添加 provider 后列表中永远是空的。

#### 根因
`stubs_api.py` 定义了 `GET /gateway/providers` 返回 `{"providers": []}`——硬编码空数组。
`api_gateway.py` 的 `GET /providers`（prefix=/v6/gateway）也映射到同路径，但反向代理 switch 读真实 provider.yaml。
FastAPI 两个路由冲突 → stub 优先 → 永远空。

#### 解决
**删除 stubs_api.py 中全部 5 个 /gateway/* 路由**。网关端点由 api_gateway.py 统一代理 switch。
同时把 `_try_include` 日志从 `logger.debug` 改为 `print`，启动时可见哪些模块加载成功/失败。

```python
# 之前（在 stubs_api.py）—— 删掉
@router.get("/gateway/providers")
async def get_gateway_providers():
    return {"providers": [], "active_provider": "", "active_model": ""}

# 之后（在 api_gateway.py）—— 真实代理 switch
@router.get("/providers")  # prefix /v6/gateway → /v6/gateway/providers
async def list_providers():
    # 从 switch 网关读 provider.yaml
```

---

### 8b. 测试连接永远 0ms

#### 现象
点击任何 provider 的"测试连接"，延迟永远 `0ms`。

#### 根因
`api_gateway.py` 的 `test_provider()` 在 switch 在线时只读缓存健康状态（`sw.get("healthy")`），不做真实 HTTP 请求。
switch 下线时才走 `OpenAIProvider.health_check()` 真测试。

#### 解决
无论 switch 在线与否，都向 provider 的 `base_url` 发 HTTP GET 测量真实延迟。
switch 不暴露 api_key（`/v1/providers` 列表不含 key）→ 改为无认证 ping base_url 根路径，测可达性+延迟。

```python
# 之前
healthy = sw.get("healthy")
return {"healthy": healthy, "latency_ms": 0}

# 之后
t0 = time.time()
with urllib.request.urlopen(f"{base_url}", timeout=5) as resp:
    resp.read()
latency = int((time.time() - t0) * 1000)
```

即使返回 401 也算"服务器可达"（`HTTPError` 被单独捕获 → healthy=True）。

---

### 8c. ProviderCard 全量抖动

#### 现象
测试连接、自动刷新 15s 轮询时，整个 provider 列表 DOM 全部重渲染，页面晃动。

#### 根因（三层递进）

1. **第一层** — `useV6Gateway` hook 的 `testProvider()` 改了全局 `data` state → 所有消费者重渲染。
   → 修复: `testingProvider` 改用本地 `useState`，不通过 hook 全局 state。

2. **第二层** — `fetchGatewayProviders` 每次轮询都 `setData(prev => ({...prev, gatewayProviders}))`，
   即使数据完全一样也触发重渲染。
   → 修复: `JSON.stringify` 比较后跳过无变化的 `setData`。

3. **第三层（根因）** — `const ProviderCard = memo(...)` 定义在 `GatewayPage` 函数体内。
   每次父组件渲染，`memo()` 被重新调用，创建**全新的** memo 组件实例 → `React.memo` 完全无效。
   → 修复: **ProviderCard 移到文件顶层**（`export function GatewayPage()` 之外）。
   `React.memo` 只创建一次，后续渲染真正进行 props 浅比较。

```tsx
// ❌ 之前 — memo 在组件体内，每次渲染重新创建
export function GatewayPage() {
  const ProviderCard = memo(({ provider }) => ( ... ));  // 每帧新建
}

// ✅ 之后 — memo 在文件顶层，只创建一次
const ProviderCard = memo(({ provider, isActive, ... }) => ( ... ));

export function GatewayPage() {
  // 使用 ProviderCard，memo 真正生效
}
```

#### 闭包陷阱
移动 ProviderCard 到顶层后，组件体内所有闭包变量（`gatewayProviders.active_model`、
`toggleExpand`、`handleTest` 等）需要改为 props 传入。遗漏任何一个 → 运行时
`xxx is not defined`。

**检查清单**: grep 终端未定义的变量 → 逐项加入 props 声明。

---

### 8d. 小记

| 错误 | 原因 | 修法 |
|------|------|------|
| 注册后列表空 | stubs shaow 了真实路由 | 删 stub，用 api_gateway.py |
| 测试 0ms | 只读缓存不实测 | HTTP GET base_url 计时 |
| 列表抖动（整体） | 全局 state 变化触发整页渲染 | memo 提到顶层 + JSON 比较跳过 |
| `gatewayProviders is not defined` | 移到顶层后闭包引用断裂 | 逐项补齐 props |

---

## 9. 前端亮暗模式切换失效 (2026-07-27)

### 9a. 现象

点击亮暗切换按钮无效，或部分区域切换了但主内容区仍然是暗色。

### 9b. 根因

三层问题叠加：

**1. CSS 层级陷阱**

```css
/* @layer base 内的规则 — 无论 !important 多强, Tailwind @layer utilities 总是覆盖它 */
@layer base {
  html.light .bg-surface-card { background-color: #FFF !important; }  /* ❌ 无效 */
}

/* 全局级（无 @layer） — 最高优先级 */
html.light .bg-surface-card { background-color: #FFF !important; }     /* ✅ 生效 */
```

Tailwind 按 `@layer` 优先级排序：`utilities > components > base`。`!important` 不能跨越层级。

**2. Vite CSS import 不打包**

```css
/* index.css 里的 @import — Vite 不解析 */
@import './light.css';  /* ❌ 不进 dist */
```

必须用 JS import：

```ts
// main.tsx
import './light.css';   /* ✅ Vite 打包进 dist */
```

**3. 类名覆盖不全**

Tailwind 生成的实际类名和源码中的类名不同：
- 源码 `hover:bg-surface-card-hover` → 生成 `.hover\:bg-surface-card-hover:hover`
- 源码 `bg-surface/50` → 生成 `.bg-surface\/50`
- 源码 `bg-surface` 是 41 处在使用的**主背景色**，之前从未覆盖

### 9c. 正确修法

不用逐类名匹配——用**属性通配选择器**覆盖全部 Tailwind 变体：

```css
/* light.css — 全局级, 无 @layer, JS import */

/* 通配: 匹配所有含 bg-surface 的类名, 包括 /50, /80 等变体 */
html.light [class*="bg-surface"]:not([class*="hover"]) { background-color: #FDFCF8 !important; }
html.light [class*="bg-surface-card"] { background-color: #FFF !important; }
html.light [class*="text-text-primary"] { color: #1F2937 !important; }

/* Tailwind 的 hover 前缀会生成独立类名, 也通配 */
html.light [class*="hover:bg-surface-card-hover"]:hover { background-color: #F3F0EB !important; }

/* 特殊类 */
html.light .bg-black\/60 { background-color: transparent !important; }
```

### 9d. 小记

| 错误 | 原因 | 修法 |
|------|------|------|
| 切换完全无效 | light.css 没打包进 dist | JS import 代替 CSS @import |
| 左右侧边栏切换了, 主内容区不变 | 只覆盖了 bg-surface-card 等类, 漏了 bg-surface(41处使用) | 属性通配选择器 `[class*="bg-surface"]` |
| hover 不变 | Tailwind 生成 `.hover\:xxx:hover`, 精确类名不匹配 | 属性通配选择器 `[class*="hover:bg-surface-card-hover"]:hover` |
|| 反复"又回到之前状态" | CSS 在 @layer base 内, !important 不生效 | 全局级(无 @layer) + JS import |

---

## §10. ReactFlow 鼠标交互完全失效 — 环境阻断 (2026-07-28)

### 10a. 现象

ReactFlow v11 画布: 键盘操作正常(方向键选择/Enter/删除偶尔生效), 所有鼠标操作(拖拽节点、平移画布、滚轮缩放、连线)完全不响应。控制台无报错。反复修改 `panOnDrag`/`nodesDraggable`/`selectionOnDrag`/`fitView`/prop 传参均无效。

### 10b. 完整调试过程(回顾性诊断)

| 迭代 | 操作 | 结果 | 问题 |
|------|------|------|------|
| 1-5 轮 | 改 panOnDrag/selectionOnDrag/nodesDraggable 开关 | 无效 | 猜测式修补 |
| 6-10 轮 | 从 useNodesState 改为受控组件 + applyNodeChanges | 无效 | 架构改变不是根因 |
| 11-15 轮 | 加 ref API/key 重挂载/条件渲染/删 useEffect #2 | 无效 | 状态同步不是根因 |
| 16-18 轮 | 注释后端调用, 纯 mock 数据测试 | 无效 | 排除数据流问题 |
| 19 轮 | 写业务流文档, 逐行追踪 500 行源码 | 无效 | 逻辑无 bug |
| **20 轮** | 最简 ReactFlow 测试页: 3 个标准节点 + fitView + Background + MiniMap, 无 TaskFlow 包装, 无自定义节点 | **无效** | ← 决定性证据 |
| 21 轮 | 切换到纯 SVG 画布(React 原生事件 + svg viewBox) | **有效** | |

### 10c. 根因推断

ReactFlow 最简版也无法响应鼠标事件, 说明问题不在我们的代码层面, 而是**环境层**:

1. **CSS 碰撞**: Tailwind preflight 或全局 CSS reset 可能覆盖了 ReactFlow 内部样式(`pointer-events`, `touch-action`, `user-select` 等)
2. **DOM 层级遮盖**: 应用壳(App shell)的某个全屏 overlay/backdrop 元素捕获了所有鼠标事件
3. **React 版本冲突**: React 19 + ReactFlow 11 可能存在事件委托不兼容
4. **Vite/Rolldown tree-shaking**: 生产构建可能丢弃了 ReactFlow 的事件处理代码

### 10d. 教训

1. **隔离测试是金律**: 问题迭代 >5 轮仍无效时, 不应继续在原代码上修补, 应立刻切到最简环境(`<ReactFlow nodes={...} />` 裸组件)隔离验证
2. **框架适配不可迷信**: ReactFlow 是成熟库, 但在特定环境下(macOS Electron + React 19 + Vite + Tailwind)可能不兼容；不兼容≠代码有 bug
3. **SVG 作为逃生舱**: 纯 SVG + React 事件 200 行代码即可实现拖拽/平移/缩放/节点编辑, 可控性远高于框架

### 10e. 替代方案对比

| 维度 | ReactFlow | 纯 SVG |
|------|-----------|--------|
| 节点拖拽 | 内置(但不响应) | `onMouseDown` + `mousemove` |
| 画布平移 | 内置(但不响应) | `viewBox` 运算 |
| 贝塞尔连线 | 内置(但不响应) | `<path>` 手动计算 |
| 缩放 | 内置(但不响应) | `viewBox` + wheel |
| 代码量 | 少 | ~200 行 |
| 调试成本 | 高(闭源内部 Store) | 低(全部可控) |
| 适配风险 | 高(框架版本/环境) | 低(标准 DOM API) |

### 10f. 2026-08-07 复核 — 真实根因（ConversationGraph 已修复）

> B5 UI 测试实测（Playwright + 自带 chromium + vite dev 同源代理）推翻
> "环境阻断"结论：ReactFlow 本身工作正常。之前的 20 轮调试被两个环境问题
> 误导，本轮全部定位并修复：

| # | 现象 | 真实根因 | 修复 |
|---|------|----------|------|
| 1 | 图谱页"收不到 pointer 事件"、节点 0 个 | **429 限流**：RateLimitMiddleware 按 `x-session-id` 分桶，前端不带 → 全部请求共享 `anonymous` 桶（burst=20, refill 1/s）；页面加载瞬时 16-18 个并发请求（health/profile/trace/abc/mind/graph/tree/objects ×2 StrictMode）直接打爆 → `getGraph().catch(()=>null)` 吞 429 → 图谱空 → 无节点可交互 | 前端全局带 `x-session-id`（sessionStorage 每标签页一身份）；后端限流默认关闭（单机模式无意义, `DM_SERVICE_ENABLE_RATE_LIMIT=1` 开启） |
| 2 | 节点渲染 20 个但拖拽/平移/右键全失败 | **fitView minZoom 钳制**：ReactFlow 默认 `minZoom=0.5`；dagre 链式布局 20 节点高 2520px，容器 525px 需要 scale≈0.17，被钳在 0.5 → 只显示图中段，首尾节点全在视口外 → 鼠标事件落在空画布 | `<ReactFlow minZoom={0.05}>` + 节点就绪后多重试 `fitView`（80/250/500/900ms, 幂等） |
| 3 | pane 平移测试恒失败 | 测试读 `viewport.getAttribute('transform')`（SVG attribute），ReactFlow v11 的 transform 是 CSS `style.transform` | 测试改读 `el.style.transform` |
| 4 | 右键菜单测试歧义 | `getByText('编辑名称')` 命中菜单按钮 + 页面提示文案两处 | 测试改 `getByRole('button', { name: '编辑名称' })` |

### 10g. 复核教训（修正 10d）

1. **先看数据通不通，再看交互**：交互测试失败时第一步是确认数据真加载（429/空响应会被 `catch(()=>null)` 静默吞掉，表现成"没事件"）
2. **fitView 不生效先查 minZoom/maxZoom**：默认 minZoom=0.5 会把大图的 fit scale 钳住，效果 = "fitView 算了但没算对"
3. **节点在视口外 ≠ 交互坏**：Playwright `toBeVisible` 只查 CSS 可见性，不查遮挡/视口外；`click` 报 "element is outside of the viewport" 时先看几何
4. 旧 §10 的"环境阻断"结论（React 19 + ReactFlow 11 不兼容）在本轮数据下不成立——当时缺的是同源代理 + 限流排查
