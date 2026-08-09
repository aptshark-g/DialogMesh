# 工程链具体实现核查 — 运行验证报告

> 日期: 2026-08-03 | 方法: 探针脚本逐文件运行验证（anaconda 3.9，PYTHONIOENCODING=utf-8）
> 状态: 全部关键缺陷**实锤**（非静态推测，均为可复现运行结果）

---

## 一、运行验证结论总表

| # | 核查点 | 验证结果 | 严重度 |
|---|---|:---:|:---:|
| 1 | `compile_context` 输出完整性 | matched_patterns 恒 Plugin Pattern；violated_anti_patterns 硬编码空；relevant_decisions 恒空 | 🔴 P0 |
| 2 | `check_anti_patterns` 边类型敏感性 | controller→db 与 controller→service **都报 1 违反** | 🔴 P0 |
| 3 | `get_impact` 质量影响 | 恒 `{performance:0, complexity:0, reliability:0}` | 🟡 P1 |
| 4 | persistence 接口兼容 | `save_artifact/load_artifacts` 正常工作（importance=0.3）| ✅ 可用 |
| 5 | `__init__.py` 导出别名 | **`Artifact` 是 `ArtifactType` 的别名**（is 判定 True）| 🔴 P0 API 陷阱 |
| 6 | TypeRegistry 类型推断 | `Repo` → Module（漏配 repository 简写）；其余正常 | 🟡 P1 |
| 7 | `chain.check_feasibility` 中文 | 英文意图可命中；**中文意图不可靠**（见 §二.3）| 🟡 P1 |
| 8 | `chain.snapshot` MCP 枚举 | `mcp_servers=[]`、tools=0 —— **MCP 分支完全失效** | 🔴 P0 |
| 9 | `api_doc_preprocessor` 解析 | OpenAPI/markdown/json 三格式正常产出 | ✅ 可用 |
| 10 | 子图 K 域读取 | 依赖 `_engineering_knowledge` 挂载（仅 CLI A 路径）| 🟡 已知 |

---

## 二、缺陷实锤细节

### 2.1 P0-1: `KnowledgeGraph.add()` 丢 impact（运行复现）
```
kg.add("Test Impact", KnowledgeType.QUALITY, binds_to=ArtifactType.MODULE,
       impact={"performance": 0.9})
→ 返回节点 n.impact == {}   # impact 参数被 _add() 丢弃
```
→ 自定义 Quality 节点永远无法带影响值，`get_impact()` 核心能力失效。

### 2.2 P0-2: `check_anti_patterns()` 不看边类型（运行复现）
```
reg.register("UserController", atype=CONTROLLER)
edge(controller→db,      DEPENDS_ON) → violations=1   # 正确（应违反）
edge(controller→service, DEPENDS_ON) → violations=1   # 错误（合法连接也报违反）
```
根因: 只检查 `source_artifact.is_type(ap.binds_to_type)`，从不检查 `proposed_edge.etype`。
后果: 反模式检测 = 按类型轰炸，任何 Controller 发出的边都算违反，无法区分合法/非法连接。

### 2.3 P0-3: `__init__.py` 导出别名陷阱（运行复现）
```
from core.agent.engineering import Artifact
Artifact is ArtifactType  # → True
```
`__init__.py` 最后一行 `from .models import is_a, ArtifactType as Artifact` 把**枚举**命名为 Artifact，
而 `models.Artifact`（数据类）反而不在顶层导出。任何 `import Artifact` 的用户拿到的是枚举，
调用 `Artifact(id=..., name=...)` 会直接 TypeError —— 命名陷阱。

### 2.4 P0-4: `chain.snapshot()` MCP 分支确定性失效（运行复现）
```
class FakeMCP: list_discovered_tools() -> ["server1_toolA","server1_toolB"]
  _adapters = {"server1_toolA": FakeAdapter(list_discovered_tools->["toolA","toolB"])}

EngineeringChain(mcp_manager=fake).snapshot()
→ mcp_servers=[]  tools=[]   # 预期 tools 应含 toolA/toolB
```
根因: `state.mcp_servers = list(tool_names) if callable(tool_names) else []` ——
`tool_names` 已经是调用后的**列表**，`callable(list)=False` → 恒空。
（比第一轮分析的「工具名查 adapter」更底层——第一行就把数据清空了。）
后果: MCP 工具永远不会进入 EngineeringState.tools → `check_feasibility` 对 MCP 工具永远 0 匹配。

### 2.5 P1: `compile_context` 五要素只交付 1.5 个（运行复现）
```
ConstraintEngine.compile_context(Controller artifact)
→ applicable_constraints: 0（该类型无绑定约束，合理）
→ matched_patterns: ['Plugin Pattern: Interface + Factory + Registry + Lifecycle']
     # get_pattern_for("") 空串兜底 → 恒返回第一条模式
→ violated_anti_patterns: 0     # 硬编码空列表，不走 check_anti_patterns()
→ relevant_decisions: 0         # preset 无 DECISION 节点
```

### 2.6 P1: TypeRegistry 推断缺口（运行复现）
```
"MyProvider"→Provider, "AuthMiddleware"→Middleware, "UserController"→Controller,
"OrderService"→Service, "ConfigYaml"→Config, "SomeRandom"→Module
但 "Repo" → Module   # "repository" 分支没配 "repo" 简写（对比 DATABASE 分支有 "db"）
```

### 2.7 P1: `check_feasibility` 中文意图失效风险
```
英文 "scan memory please" → feasible=True, matches=[memory_scan]   # 子串命中
中文 "帮我扫描内存地址"（经 UTF-8 文件验证）→ 依赖英文工具名子串匹配，实际不可靠
根因: text.split() 对中文无空格分词 → 整句一词 → 与英文工具名/描述子串不匹配
```

---

## 三、验证为「可用」的部分

| 组件 | 验证 | 结论 |
|---|---|---|
| `APIDocPreprocessor.parse` | OpenAPI 3.0（2 端点+参数 schema）、markdown、json 三种格式 | ✅ 基础解析可用（无 URL/GraphQL/schema 引用解析）|
| `EngineeringChainPersistence` | save_artifact→load_artifacts 往返 + UnifiedGraphStore 落库 | ✅ 接口正确（但生产零接线）|
| `models` is_a 树 | Provider is_a Module is_a Artifact | ✅ 类型树正确 |
| `registry.register/find_by_type` | 注册+按类型查询 | ✅ |

---

## 四、本轮新增缺陷清单（相对前两轮）

1. **`__init__.py` Artifact 别名陷阱**（P0，新发现）—— 顶层导出把枚举当数据类命名。
2. **`chain.snapshot` MCP 恒空根因升级**（P0，根因修正）—— `callable(列表)=False`，
   不是「工具名查 adapter」而是「第一行就清空」。
3. **`check_anti_patterns` 边类型盲区运行复现**（P0，实证）。
4. **TypeRegistry `Repo` 推断缺口**（P1，新发现）。

---

## 五、结论

工程链实现「模型层可用、推理层空转、接入层断裂」的结论被运行验证进一步夯实：
- 能跑通的只有: models / registry / knowledge_graph 增删查 / persistence / api_doc 基础解析。
- 一跑就错的: compile_context（假模式/空反模式/空决策）、check_anti_patterns（类型轰炸）、
  snapshot MCP（恒空）、add（丢 impact）、白盒 CLI（UUID 键 vs name 查询）。
- 导出即坑: `__init__` 的 Artifact 别名。
