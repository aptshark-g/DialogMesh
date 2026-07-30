# DialogMesh CLI 参考手册 v6.1

> 最后更新: 2026-07-30 · 128/173 命令 (74%)

## 模块状态

| 模块 | 完成度 | 引擎依赖 | 备注 |
|------|:------:|----------|------|
| engine | 100% | _state | 启动/状态/链/统计/停止 |
| session | 100% | v3_sessions.json | 新建/列表/切换/信息/历史/导出/删除 |
| discourse | 75% | _discourse_tree, _topic_tree | 12/16: 缺 split/merge/delete/promote CLI包装 |
| pcr | 100% | _pcr_router | 路由/配置/历史/set/reset |
| intent | 100% | _pcr_router, _last_intent | 解析/展示/历史/置信度 |
| context | 100% | _last_context | 展示 |
| subgraph | 100% | _subgraph | 展示/展开 |
| blueprint | 43% | BlueprintEngine | 7/16: show/build/validate/export + decider |
| decider | 100% | _decider | 展示/链/执行 |
| behavior | 55% | _behavior_graph_adapter | 5/9: 展示/预测/统计/历史/重置 |
| meta | 62% | _meta_cognition | 5/8: 展示/审查/审计/验证/统计 |
| assoc | 62% | _l1_modifier, _l2_5_belief | 5/8: 展示/追踪/漏斗/统计/过滤 |
| obs | 100% | _observation_pool | 9/9: 全功能 |
| profile | 54% | _ocean_analyst (可选) | 6/11: 展示/编辑/OCEAN/特征/历史/重置 |
| engineering | 16% | _engineering_knowledge (可选) | 1/6: 仅展示 |
| concepts | 20% | (无引擎数据) | 1/5: 仅展示 |
| mind | 12% | (无引擎数据) | 1/8: 仅展示 |
| rules | 30% | (磁盘JSON) | 3/10: 展示/添加/统计 |
| abc | 100% | (磁盘JSON) | 展示 |
| annotations | 41% | (磁盘JSON) | 5/12: 展示 + write_cmd的add等 |
| corrections | 100% | (磁盘JSON) | 展示 |
| feedback | 100% | (磁盘JSON) | 展示 |
| inertia | 100% | _inertia | 展示/模式 |
| versions | 100% | (磁盘JSON) | 展示 |
| metrics | 100% | (磁盘JSON) | 展示 |
| knowledge | 55% | _rag_bridge, _frame_library | 5/9: 查询/来源/导入/+write_cmd |
| task | 91% | _task_graph (磁盘) | 11/12: node/edge CRUD + show |
| learning | 60% | _learning_sources, _content_fetcher | 搜索/抓取/(CLI待加) |

---

## 引擎 (5/5 ✅)

```bash
dm engine start [--provider mock|deepseek|gateway]
dm engine status            # → {"running": true, "subsystems": 37}
dm engine chains            # → {"chains": {...}}
dm engine stats             # → 启动耗时、子模块统计
dm engine stop
```

## 会话 (7/7 ✅)

```bash
dm session new              # → {"session_id": "abc123"}
dm session list             # → [{"id":"abc","turns":3,...}]
dm session use <id>         # 切换活跃会话
dm session info [<id>]      # → {"session_id":...,"turns":3}
dm session history [<id>]   # → [{"role":"user","content":"..."}]
dm session export [<id>]    # 导出到 data/session_<id>.json
dm session delete [<id>]    # 从 v3_sessions.json 删除
```

## 对话树 (12/16 ✅)

```bash
dm discourse show [--sid <id>]         # 块统计
dm discourse tree [--sid <id>]         # 块关系树
dm discourse block <block_id>          # 单个块详情
dm discourse feed <text>               # 喂入文本→EDU切分
dm discourse search <keyword>          # 搜索块
dm discourse stats [--sid <id>]        # 统计(引擎+磁盘兜底)
dm discourse compress [--sid <id>]     # 冷压缩
dm discourse topics [--sid <id>]       # 话题热图
dm discourse topic-tree [--sid <id>]   # 话题树
dm discourse summary <id> <text>       # 设置块摘要
dm discourse topic-add <topic>         # 添加话题
dm discourse topic-remove <topic>      # 移除话题
```

## PCR (6/6 ✅) + 意图 (7/7 ✅) + 上下文 (3/3 ✅)

```bash
# PCR
dm pcr route <text>           # 路由分析
dm pcr config                 # 查看配置
dm pcr history                # PCR历史
dm pcr set-config <k> <v>     # 修改配置
dm pcr reset-config           # 重置

# 意图
dm intent parse <text>        # 解析意图
dm intent show                # 最后解析结果
dm intent history             # 意图历史
dm intent confidence          # 置信度 + PCR zone

# 上下文
dm context show               # 编译后的上下文IR
```

## Subgraph (2/2 ✅)

```bash
dm subgraph show               # 当前子图
dm subgraph expand <text>      # 从文本展开子图
```

## Blueprint + Decider (7/16 ⚠️)

```bash
# Blueprint
dm blueprint show              # DAG 节点+边
dm blueprint build <text>      # 模板DAG
dm blueprint validate          # 验证计划
dm blueprint export            # 导出DAG JSON

# Decider
dm decider show                # 决策器状态
dm decider chains              # 链状态
dm decider execute             # 执行当前DAG
```

## 认知模块 P3 (behavior/meta/assoc/obs)

### Behavior (5/9)
```bash
dm behavior show               # 行为图状态
dm behavior predict <text>     # 预测
dm behavior stats              # 统计
dm behavior history            # 最近链路
dm behavior reset              # 重置
```

### Meta (5/8)
```bash
dm meta show                   # 元认知状态
dm meta review                 # 复盘审查
dm meta audit                  # 自我审计 (self_audit)
dm meta verify                 # 验证过往决策
dm meta stats                  # 统计
```

### Association (5/8)
```bash
dm assoc show                  # 关联链状态
dm assoc trace                 # 追踪
dm assoc funnel                # L1/L2.5 层级
dm assoc stats                 # L2.5 统计
dm assoc filter                # 信念计数
```

### Observation (9/9 ✅)
```bash
dm obs show                    # 池统计 (total_bundles/consumed)
dm obs query <domain>          # 按域查询
dm obs stats                   # 详细统计
dm obs list                    # 全部观察
dm obs clear                   # 清空
dm obs filter <domain>         # 域过滤计数
dm obs mark <event_id>         # 标记已消费
dm obs reset                   # 重置池
dm obs subscribe               # 订阅
```

## 画像/工程 P4 (9/30 ⚠️)

```bash
# 画像
dm profile show                # OCEAN快照 (如果有ocean_analyst)
dm profile edit <dim> <val>    # 编辑维度
dm profile ocean               # OCEAN 5维
dm profile traits              # 扩展特征
dm profile history             # OCEAN历史
dm profile reset               # 重置

# 工程/概念/Mind (引擎数据缺失)
dm engineering show            # 工程知识图
dm concepts show               # 概念图
dm mind show                   # 注意力/锚点
```

## 规则/注解 P5 (11/38 ⚠️)

```bash
dm rules show                  # 规则列表 (JSON)
dm rules add <name> <value>    # 添加规则
dm rules stats                 # 引擎状态
dm abc show                    # ABC原因链
dm annotations show            # 注解
dm corrections show            # 修正
dm feedback show               # 反馈
dm inertia show                # 惰性状态
dm inertia patterns            # 惰性模式
dm versions show               # 版本
dm metrics show                # 度量
```

## 知识图谱 (5/9 ✅)

```bash
dm knowledge query <keyword>   # RAG查询
dm knowledge sources           # 知识来源
dm knowledge import <file>     # 从JSON导入
dm knowledge add <k> <v>       # 添加 (write_cmd)
dm knowledge remove <k>        # 删除 (write_cmd)
```

## 任务图 (11/12 ✅)

```bash
dm task show [--sid <id>]      # 显示任务图
dm task node add <name> [--deps=id]
dm task node edit <id> <k=v>
dm task node remove <id>
dm task edge add --from <id> --to <id>
dm task edge remove <id>
dm task save [--input <file>]
dm task confirm [--sid <id>]
```

---

## 引擎属性映射

CLI 命令 → 引擎属性 → 必需?

| 命令组 | 引擎属性 | 状态 |
|--------|----------|:----:|
| discourse | `_discourse_tree`, `_topic_tree` | ✅ |
| pcr/intent/context | `_pcr_router`, `_last_intent`, `_last_context` | ✅ |
| behavior | `_behavior_graph_adapter` | ✅ |
| meta | `_meta_cognition` | ✅ |
| assoc | `_l1_modifier`, `_l2_5_belief` | ✅ |
| obs | `_observation_pool` | ✅ |
| profile | `_ocean_analyst` | ⚠️ |
| knowledge | `_rag_bridge`, `_frame_library` | ✅ |
| blueprint | `_blueprint_engine` (未接) | ⚠️ |
| engineering | `_engineering_knowledge` (未接) | ⚠️ |
| concepts/mind | 无 | ❌ |
| inertia | `_inertia` | ✅ |
| rules/abc/annotations | `data/*.json` (磁盘) | ⚠️ |
| task | `_task_graph` (磁盘) | ✅ |
| learning | `_learning_sources`, `_content_fetcher` | ✅ |

---

## 阶段3: 深层接口待建

以下模块需要新引擎内部API后才能补全CLI:

| 模块 | 缺失能力 | 优先级 |
|------|---------|:---:|
| blueprint | build_hybrid, PlanGate, execution | 高 |
| engineering | 知识图读写、查询 | 中 |
| concepts | 概念图CRUD | 中 |
| mind | 注意力/锚点/错误读 | 中 |
| rules | 搜索/过滤/导出/清除 | 低 |
| annotations | 批量操作/导出 | 低 |
| profile | OCEAN持久化、对比 | 高 |
| blueprt-exec | DAG执行验证 | 高 |
