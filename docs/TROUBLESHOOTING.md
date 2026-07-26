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

## 7. 前端崩盘 — stub ↔ TS 类型不一致 (重复 4+ 次, 2026-07-26)

### 现象
```
TypeError: t.map is not a function        (DashboardPage)
TypeError: Cannot convert undefined or null to object  (CognitiveProfilePage)
TypeError: Cannot read properties of undefined (reading 'total_patterns')  (BehaviorPage)
TypeError: Cannot read properties of undefined (reading 'map')  (GatewayPage)
```

### 根因
前后端类型不同步。Python stub 返回 `{"profile": {"oceAN_dims": {...}}}` 但 TS 类型声明了 `V6ProfileResponse = { oceAN_dims: ... }`（顶层字段）。AI Agent 凭直觉编造 stub 格式而非对照 TS 源码。
- 画像：`oceAN_dims` 嵌套在 `profile` 下 → component 读 `data.oceAN_dims` 为 `undefined`
- 行为：缺少 `total_patterns` 字段 → component 读 `data.total_patterns` → `undefined`
- 网关：返回 `[]` 裸数组 → component 期望 `{providers: [], active_provider: ""}`

### 根因 — AI Agent 缺陷
Agent 在"看前端"和"写后端"两步之间断开上下文：
1. Agent 看到 frontend defs (`getSessions(): Promise<V6SessionListItem[]>`) 
2. 但写 Python stub 时不交叉校验 `V6SessionListItem` 实际字段
3. 猜测格式 (`{"sessions": [], "count": 0}`) 而非直接读取 `src/types/api.ts`

### 解决
(2026-07-26) 全线重写 stubs_api.py，每个端点逐一对标 `frontend/src/types/api.ts` 中的 V6*Response 接口。
从现在开始，任何改动的纪律：
1. **先读 src/types/api.ts** 对应 V6*Response 定义
2. **Python 返回 dict 字段名逐字匹配 TS 字段**
3. 不假设、不猜测、不自行包装外层 key

### 经验
```
错误模式: 前端 GET /v6/xxx 200 → resp.json() → TS component 解构失败 → ErrorBoundary
规律: console 报 TypeError: *.map is not a function 或 Cannot read * of undefined
→ 直接 grep TS type 定义 → stub 字段 vs type 字段 diff → 修复
```

### 42 端点完整对标表
```
端点               TS 返回类型            Python stub 格式
/profile          V6ProfileResponse      {oceAN_dims, mbti, turn_count, ...}  ← 顶层!
/trace            V6TraceResponse        {reason_distribution, avg_confidence, total}
/abc              V6AbcResponse          {} (Record)
/mind             V6MindResponse         {} (Record)
/graph            V6GraphResponse        {nodes, edges, subgraph_nodes}
/discourse-tree   V6DiscourseTreeResponse {blocks, total}
/objects          V6ObjectsResponse      {nodes, edges, total_objects}
/rules            V6RulesResponse        {rules, total}
/relations        V6RelationsResponse    {} (Record)
/causal           V6CausalResponse       {} (Record)
/behavior         V6BehaviorResponse     {} (Record)
/behavior/patterns 自定义                 {total_patterns, patterns, frequency_by_type}
/engineering      V6EngineeringResponse  {} (Record)
/pipeline         V6PipelineResponse     {} (Record)
/extraction       V6ExtractionResponse   {} (Record)
/perspectives     V6PerspectivesResponse {} (Record)
/parameters       自定义                  {} (Record)
/context           自定义                  {} (Record)
/subgraph           自定义                  {} (Record)
/subgraph/cache   自定义                  {hit_rate, total_queries}
/persistence        V6PersistenceResponse {annotation_store, unified_store, oceAN_saved, rules_saved}
/persistence/graphs  V6SessionListItem[] []  (裸数组!)
/sessions          V6SessionListItem[]    []  (裸数组!)
/provider          V6ProvidersResponse    {active, failover}
/router/modes      V6RouterModesResponse  {available, modes, active, force_mode, disabled}
/metrics           V6MetricsResponse      {} (Record)
/gateway/providers  V6GatewayProvidersResponse {providers, active_provider, active_model}
/gateway/config      自定义                {config, stats}
/gateway/usage       自定义                {all_sessions: {by_provider: {}}}
/gateway/stats       自定义                {providers, active, requests, errors_by_provider}
/gateway/health      自定义                {status, gateway, circuits, engine_status}
/inertia            {by_weight, total}
/degradation        {level, score}
/ttl               {ttl_stats, total}
/recursive-map      {map, count}
/engineering/modules {modules, count}
/meta/stats         {stats, self_audit}
/meta/queue         {queue, pending}
/versions/profile   {versions, current}
```
