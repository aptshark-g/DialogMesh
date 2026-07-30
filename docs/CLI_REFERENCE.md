# DialogMesh CLI 参考手册 v6

> 自动生成 2026-07-30 · 前端联调使用

## 快速开始

```bash
# 启动引擎 (自动检测 provider)
dm engine start

# 查看状态
dm engine status

# 查看所有子系统链
dm engine chains
```

---

## 模块速查

| 模块 | 命令数 | 已实现 | 状态 |
|------|--------|--------|:----:|
| 引擎 engine | 5 | 5 | ✅ |
| 会话 session | 7 | 3 | ⚠️ |
| 对话树 discourse | 16 | 16 | ✅ |
| PCR 路由 pcr | 6 | 6 | ✅ |
| 意图 intent | 7 | 7 | ✅ |
| 上下文 context | 3 | 3 | ✅ |
| 子图 subgraph | 2 | 2 | ✅ |
| Blueprint blueprint | 16 | 7 | ⚠️ |
| Decider decider | 3 | 3 | ✅ |
| 元认知 meta | 5 | 5 | ✅ |
| 行为链 behavior | 5 | 5 | ✅ |
| 关联链 assoc | 5 | 5 | ✅ |
| 观察池 obs | 9 | 8 | ⚠️ |
| 画像 profile | 6 | 6 | ⚠️ |
| 工程图 engineering | 1 | 1 | ⚠️ |
| 概念图 concepts | 1 | 1 | ⚠️ |
| Mind | 1 | 1 | ⚠️ |
| 规则 rules | 3 | 3 | ⚠️ |
| 惰性 inertia | 2 | 2 | ⚠️ |
| 任务图 task | 12 | 11 | ⚠️ |
| 知识图谱 knowledge | 5 | 5 | ✅ |
| 学习 intake learning | 3 | 3 | ✅ |

**当前: ~88/180 命令 (49%)**

---

## 一、引擎 (5 commands)

```bash
dm engine start [--provider mock|deepseek|gateway] [--model <name>] [--key <api_key>]
dm engine status
dm engine chains
dm engine stats
dm engine stop
```

## 二、会话 (3/7)

```bash
dm session list
dm session current
dm session switch <sid>
```

## 三、对话树 (16/16 ✅)

```bash
dm discourse show [--sid <id>]
dm discourse tree [--sid <id>]
dm discourse block <block_id> [--sid <id>]
dm discourse feed <text>
dm discourse search <keyword>
dm discourse stats [--sid <id>]
dm discourse compress [--sid <id>]
dm discourse topics [--sid <id>]
dm discourse topic-tree [--sid <id>]
dm discourse summary <block_id> <text>
dm discourse topic-add <topic>
dm discourse topic-remove <topic>
```

## 四、PCR (6/6 ✅)

```bash
dm pcr route <text>
dm pcr config
dm pcr config set <key> <value>
dm pcr config reset
dm pcr history
```

## 五、意图 (7/7 ✅)

```bash
dm intent parse <text>
dm intent show
dm intent history
dm intent confidence
```

## 六、Subgraph (2/2 ✅)

```bash
dm subgraph show
dm subgraph expand <text>
```

## 七、Blueprint (7/16)

```bash
dm blueprint show
dm blueprint build <text>
dm blueprint validate
dm blueprint export
dm decider show
dm decider chains
dm decider execute
```

## 八、认知模块 (P3 — 22 commands)

```bash
# Behavior
dm behavior show
dm behavior predict <text>
dm behavior stats
dm behavior history
dm behavior reset

# Meta
dm meta show
dm meta review
dm meta audit
dm meta verify
dm meta stats

# Association
dm assoc show
dm assoc trace
dm assoc funnel
dm assoc stats
dm assoc filter

# Observation
dm obs show
dm obs query <domain>
dm obs stats
dm obs list
dm obs clear
dm obs filter <domain>
dm obs mark <event_id>
```

## 九、画像/工程 (P4 — 9 commands)

```bash
dm profile show
dm profile edit <dimension> <value>
dm profile ocean
dm profile traits
dm profile history
dm profile reset
dm engineering show
dm concepts show
dm mind show
```

## 十、规则/注解 (P5 — 11 commands)

```bash
dm rules show
dm rules add <name> <value>
dm rules stats
dm abc show
dm annotations show
dm corrections show
dm feedback show
dm inertia show
dm inertia patterns
dm versions show
dm metrics show
```

## 十一、知识图谱 (5 commands)

```bash
dm knowledge query <keyword>
dm knowledge sources
dm knowledge import <file>
dm knowledge add <key> <value>
dm knowledge remove <key>
```

## 十二、任务图 (11/12)

```bash
dm task show [--sid <id>]
dm task node add <name> [--deps <id,id>]
dm task node edit <id> <key=val>
dm task node remove <id>
dm task edge add --from <id> --to <id>
dm task edge remove <id>
dm task save [--input <file>]
dm task confirm [--sid <id>]
```

---

## 输出格式

所有命令输出 JSON，stderr 输出日志 (可 `2>/dev/null` 忽略):

```bash
dm engine status 2>/dev/null
# → {"running": true, "subsystems": 37, "provider": "mock"}
```

## 引擎依赖

CLI 命令依赖的引擎属性 (`_engine.<attr>`):

| 命令组 | 引擎属性 | 必需? |
|--------|---------|:----:|
| discourse | `_discourse_tree`, `_topic_tree` | ✅ |
| pcr/intent | `_pcr_router`, `_last_pcr`, `_last_intent` | ✅ |
| behavior | `_behavior_graph_adapter` | ✅ |
| meta | `_meta_cognition` | ✅ |
| assoc | `_l1_modifier`, `_l2_5_belief` | ✅ |
| obs | `_observation_pool` | ✅ |
| profile | `_ocean_analyst` | ⚠️ fallback |
| knowledge | `_rag_bridge`, `_frame_library` | ⚠️ fallback |
| blueprint | `_blueprint_engine` | ⚠️ fallback |
| task | `_task_graph` | ⚠️ fallback |

---

## 前端集成

前端通过 `/v6/` REST API 获取实时数据。CLI 用于调试和自动化。

对应关系见 `DESIGN_FRONTEND_CLI_MAPPING.md`:
- Chat → `/v3/session/{id}/message`
- Sessions → `/v6/sessions`
- Profile → `/v6/profile`
- Graph → `/v6/graph` + `/v6/discourse-tree`
- Pipeline → `/v6/trace`
- Tasks → `/v3/session/{id}/task_graph`
- Behavior → `/v6/behavior`
- Mind → `/v6/mind`
- ABC → `/v6/abc`
- Engineering → `/v6/engineering`
