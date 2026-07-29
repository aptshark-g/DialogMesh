# DialogMesh v6 — 交互式图编辑 & 子图上下文设计

> v1.0 | 2026-07-29
> 核心思想: 图的编辑能力不是功能点，是用户对 LLM 上下文的控制权。
> 一处设计，四处复用：DiscourseTree / KnowledgeGraph / Subgraph / PersistentGraph。

---

## 一、架构定位

```
┌─────────────────────────────────────────────────┐
│                   用户 (浏览器)                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 对话树图  │  │ 知识对象图 │  │ 子图 (上下文)   │  │
│  │ (分支/合并)│  │ (关系/层级)│  │ (LLM 输入窗口)  │  │
│  └────┬─────┘  └────┬─────┘  └───────┬───────┘  │
│       │             │               │           │
│       └─────────────┼───────────────┘           │
│                     │                           │
│              ┌──────▼──────┐                    │
│              │  GraphEditor │  ← 统一编辑组件     │
│              │ (右键/拖拽/   │                    │
│              │  双击/框选)   │                    │
│              └──────┬──────┘                    │
└─────────────────────┼───────────────────────────┘
                      │
┌─────────────────────┼───────────────────────────┐
│              后端 (FastAPI :8000)                 │
│       ┌──────────┴──────────┐                   │
│       │   Graph CRUD API     │                   │
│       │  POST node/add       │                   │
│       │  POST edge/add       │                   │
│       │  POST subgraph/compile│  ← 触发 LLM       │
│       └──────────┬──────────┘                   │
│                  │                               │
│       ┌──────────▼──────────┐                   │
│       │   SubgraphCompiler   │                   │
│       │   + ContextAssembler │                   │
│       │   → LLM prompt       │                   │
│       └─────────────────────┘                   │
└─────────────────────────────────────────────────┘
```

## 二、统一 GraphEditor 交互模型

### 2.1 核心操作

| 操作 | 手势 | CLI 等价 | 适用图类型 |
|------|------|---------|----------|
| **选择** | 单击节点 | `dm graph node <id>` | 全部 |
| **编辑** | 双击节点 → inline 编辑 | `dm graph node-edit <id>` | 全部 |
| **展开/折叠** | 单击 +/- 图标 | `dm subgraph expand <anchor>` | 子图 |
| **添加节点** | 右键空白 → "添加" 或 快捷键 N | `dm graph node-add <name>` | 全部 |
| **删除节点** | 右键节点 → "删除" 或 Delete | `dm graph node-remove <id>` | 全部 |
| **连线** | 拖拽节点 A → 节点 B | `dm graph edge-add <a> <b>` | 全部 |
| **断线** | 右键边 → "删除" | `dm graph edge-remove <id>` | 全部 |
| **拆分** | 右键 discourse 节点 → "拆分" | `dm ds split <block-id>` | 对话树 |
| **合并** | 框选 2 个节点 → 右键 "合并" | `dm ds merge <a> <b>` | 对话树 |
| **提升/降级** | 右键 → "提升/降级" | `dm ds promote/demote` | 对话树/子图 |
| **框选** | Shift+拖拽 | N/A | 全部 |
| **复制到子图** | 右键 → "加入上下文" | `dm subgraph node <id>` | 对话树/知识图 |
| **从子图移除** | 右键 → "移出上下文" | N/A | 子图 |
| **编译上下文** | 工具栏 "→ LLM" 按钮 | `dm context compile` | 子图 |

### 2.2 右键菜单

```
┌──────────────────────┐
│ 📝 编辑内容           │  ← 双击
│ ➕ 添加子节点         │
│ ✂️  拆分 (discourse)  │
│ 🔗 合并 (框选2个)     │
│ ⬆️  提升 (设为活跃)    │
│ ⬇️  降级 (降温)       │
│ ─────────────────── │
│ 📋 复制到子图上下文    │  ← 核心复用点
│ 🔍 从此节点展开子图    │  ← k-hop BFS
│ ─────────────────── │
│ 🗑️  删除             │
└──────────────────────┘
```

### 2.3 四种图的数据源

| 图类型 | 数据源 | 节点含义 | 边含义 | 可编辑 |
|--------|--------|---------|--------|--------|
| **对话树图** | DiscourseBlockTree | block (对话片段) | parent/child、fork | ✅ split/merge/promote/demote |
| **知识对象图** | world_objects + knowledge | 概念/实体/文件 | depends/creates/constrains | ✅ add/remove node & edge |
| **子图** | SubgraphCompiler 编译结果 | 被选入上下文的节点 | 选中节点间的关系 | ✅ 增删节点 (改变 LLM 输入) |
| **持久化图** | PersistentGraph / v3_sessions | 历史会话节点 | 会话间关联 | ✅ 编辑历史 |

---

## 三、子图：用户控制 LLM 上下文

### 3.1 为什么子图是关键

```
传统 LLM:  系统提示 + 最近 N 条消息 → 固定窗口
子图方式:  用户手动选择节点/概念 → 精确控制上下文
           LLM 收到的 context = 子图中所有节点 + 边 + 权重
```

**自由度对比**：

| | 传统上下文 | 子图上下文 |
|---|---|---|
| 范围控制 | 只能控制 token 数 | 精确选择哪些概念/对话/知识点 |
| 结构 | 线性消息历史 | 有向图 (概念间关系) |
| 深度 | 只有最近的 N 条 | 沿边展开 k-hop, 跳数可调 |
| 用户在环 | ❌ 被动接受 | ✅ 主动塑造 |

### 3.2 子图编辑工作流

```
1. 用户在对话树图或知识图中浏览
2. 选中需要的节点 → 右键 "复制到子图上下文"
3. 切换到子图视图 → 看到已选节点及它们的关系
4. 可继续: 展开节点 (k-hop)、添加/删除节点、调整权重
5. 满意后 → 点 "编译上下文" 或 "发送给 LLM"
6. 后端 SubgraphCompiler 将子图转为结构化 LLM prompt
7. LLM 回复基于这个精确的上下文窗口
```

### 3.3 子图后端

```
POST /v6/subgraph/compile
  body: { nodes: ["id1","id2"], edges: [...], max_hops: 2, format: "xml" }
  → SubgraphCompiler.expand(anchor, nodes, edges)
  → ContextAssembler.compile(subgraph)
  → LLM prompt injection

GET /v6/subgraph/current
  → 返回当前子图状态 (nodes, edges, anchored)

POST /v6/subgraph/node/add
POST /v6/subgraph/node/remove
POST /v6/subgraph/edge/add
POST /v6/subgraph/edge/remove
```

---

## 四、持久化与复用

### 4.1 子图持久化

每次编译上下文时，子图自动保存：

```
data/subgraphs/
  ├── 2026-07-29-001.json   ← 子图快照
  ├── 2026-07-29-002.json
  └── current.json          ← 当前子图状态
```

子图可命名、可列表、可回退：
- `dm subgraph save <name>` 命名保存
- `dm subgraph list` 查看所有
- `dm subgraph load <name>` 恢复

### 4.2 复用场景

| 场景 | 复用方式 |
|------|---------|
| 追问同一主题 | `dm subgraph load "登录系统设计"` → 恢复上次上下文 |
| 跨会话迁移 | 导出子图 JSON → 新会话导入 |
| A/B 测试 | 不同子图配置 → 同一个 prompt → 对比 LLM 输出 |
| 团队协作 | 分享子图 JSON → 同事用相同上下文复现 |

---

## 五、实施路径

```
Phase A: 图数据修复 (0.5h)
  A1. /v6/graph 端点改为返回 discourse block 节点+关系
  A2. /v6/objects 端点返回知识对象 + 关联

Phase B: GraphEditor 基础 (1.5h)
  B1. ReactFlow v11 画布组件
  B2. 节点渲染 (block 摘要 / 概念名 / 温度色标)
  B3. 边渲染 (关系类型标签)
  B4. 双击编辑 / 拖拽连线 / Delete 删除

Phase C: 右键菜单 (0.5h)
  C1. ContextMenu 组件
  C2. 对话树操作 (split/merge/promote/demote)
  C3. 子图操作 (复制到上下文/展开/移除)

Phase D: 子图集成 (1h)
  D1. 子图视图切换
  D2. 子图编译 → LLM prompt
  D3. 子图持久化 (save/load/list)

Phase E: 知识对象图 (0.5h)
  E1. 知识对象视图
  E2. 知识关系 CRUD
  E3. 对象搜索 → 加入子图
```

---

## 六、CLI 对等命令 (全部已有)

子图相关 CLI 完全就绪：
```
dm subgraph show                    → 当前子图
dm subgraph expand <anchor>         → k-hop 展开
dm subgraph hop <N>                 → 设跳数
dm subgraph weight <type> <w>       → 设边权重
dm subgraph budget <tokens>         → token 预算
dm subgraph strategy                → 当前策略
dm subgraph strategy set <s>        → 切换策略
dm subgraph node <id>               → 查看节点
dm subgraph path <from> <to>        → 两节点路径
dm context compile                  → 编译子图为 LLM 输入
dm context show                     → 查看编译结果
```

前端 GraphEditor 本质是这些 CLI 命令的可视化 + 交互版本。
