# DialogMesh CLI — 白盒化完整设计

> v3.0 | 2026-07-28
> 每模块均可查看、可修改、可回溯。Unix 管道，stdin/stdout JSON。

---

## 一、约定

- stdin/stdout JSON，stderr 日志
- CRUD = show/get/add/edit/delete (or save)
- `[ALL]` = 所有会话, `[SID]` = 当前会话
- 退出码: 0=成功, 1=引擎未启动, 2=模块错误, 3=参数错误

---

## 二、引擎

| 命令 | 功能 |
|------|------|
| `dm engine start` | 启动 CRG，加载 provider + 设计文档 |
| `dm engine stop` | 停止 |
| `dm engine status` | 全状态：running/chains/pool/graph/event_count |
| `dm engine chains` | 10 链各自状态 (✅/⚠️/❌) |
| `dm engine stats` | Async Path 统计（调用次数/延迟/成功率） |

---

## 三、会话

| 命令 | 功能 |
|------|------|
| `dm session new` | 创建 |
| `dm session list` | 列表 |
| `dm session use <id>` | 切换 |
| `dm session info` | 详情 |
| `dm session history` | 消息历史 |
| `dm session clear` | 清空 (不删文件) |
| `dm session delete <id>` | 删除会话 + task_graph |

---

## 四、对话树 (DiscourseBlockTree)

| 命令 | 功能 |
|------|------|
| `dm discourse show` | 对话树概览：block 数/深度/当前分支 |
| `dm discourse tree` | 完整树 JSON (blocks + children + parent) |
| `dm discourse block <id>` | 读取单个 block：EDUs/温度/摘要/实体 |
| `dm discourse feed <text>` | 喂文本 → 生成 blocks |
| `dm discourse search <keyword>` | 搜索 block 内容/实体 |
| `dm discourse split <block-id>` | 手动拆分 block |
| `dm discourse merge <id1> <id2>` | 合并两个 block |
| `dm discourse delete <block-id>` | 删除 block (子 block 上移) |
| `dm discourse promote <block-id>` | 设为活跃 (temperature=0) |
| `dm discourse demote <block-id>` | 降温 (temperature→3) |
| `dm discourse compress` | 触发冷压缩 (cold→summary) |
| `dm discourse summary <block-id> <text>` | 手动设置摘要 |
| `dm discourse topic show` | 话题树快照 |
| `dm discourse topic add <topic>` | 手动添加话题 |
| `dm discourse topic remove <topic>` | 删除话题 |
| `dm discourse topic heat` | 话题热度排名 |

---

## 五、PCR (预认知路由)

| 命令 | 功能 |
|------|------|
| `dm pcr route <text>` | 路由分析：zone/expectation/noise/complexity |
| `dm pcr show` | 最近 PCR 结果 |
| `dm pcr config` | PCR 配置：阈值/zone 映射 |
| `dm pcr config set <key> <val>` | 修改配置项 |
| `dm pcr config reset` | 重置默认配置 |
| `dm pcr history` | PCR 历史 |

---

## 六、意图 (Intent)

| 命令 | 功能 |
|------|------|
| `dm intent parse <text>` | 意图解析：segments/entities/ambiguities |
| `dm intent config` | 配置：意图类型/置信度阈值 |
| `dm intent config set <key> <val>` | 修改配置 |
| `dm intent segment add <text>` | 手动添加意图 segment |
| `dm intent segment remove <id>` | 删除意图 segment |
| `dm intent entity add <type> <value>` | 手动添加实体 |
| `dm intent entity remove <value>` | 删除实体 |

---

## 七、上下文 (ContextCompiler)

| 命令 | 功能 |
|------|------|
| `dm context compile` | 编译 ContextIR (当前会话) |
| `dm context show` | 最近编译结果 |
| `dm context entry <idx>` | 查看某条 entry |
| `dm context add <type> <domain> <content>` | 手动注入 entry |
| `dm context remove <idx>` | 删除 entry |
| `dm context subgraph <entity>` | 子图裁剪 |
| `dm context tokens` | Token 使用统计 |

---

## 八、Blueprint + Decider

| 命令 | 功能 |
|------|------|
| `dm blueprint build` | 从意图构建 DAG |
| `dm blueprint show` | 当前 DAG: nodes + edges |
| `dm blueprint node <id>` | 查看节点详情 |
| `dm blueprint node add <chain> [--parent=<id>]` | 添加节点 |
| `dm blueprint node remove <id>` | 删除节点 |
| `dm blueprint node edit <id> <key=val>...` | 修改节点属性 |
| `dm blueprint edge add <from> <to> [--required]` | 添加边 |
| `dm blueprint edge remove <from> <to>` | 删除边 |
| `dm blueprint edge required <from> <to> <bool>` | 设置依赖必需性 |
| `dm blueprint strategy` | 当前策略 + 可用策略 |
| `dm blueprint strategy set <name>` | 切换策略 |
| `dm decider execute` | 执行当前 DAG |
| `dm decider show` | 最近执行结果 |
| `dm decider tick <N>` | 查看某个 Tick 结果 |
| `dm decider chain <name>` | 查看某链输出 |
| `dm decider chains` | 12 链状态 |

---

## 九、LLM 回复

| 命令 | 功能 |
|------|------|
| `dm reply generate` | 从上下文生成回复 |
| `dm reply show` | 最近回复 |
| `dm reply raw <prompt>` | 裸 LLM 调用 |
| `dm reply model` | 当前模型 |
| `dm reply model set <name>` | 切换模型 |
| `dm reply instances` | 6 个 LLM 实例状态 (pcr/intent/planning/meta/answer/reflective) |
| `dm reply instance <name> <text>` | 调用指定实例 |

---

## 十、元认知 (Meta)

| 命令 | 功能 |
|------|------|
| `dm meta review` | 复盘：anomalies/corrections/score |
| `dm meta show` | 最近复盘结果 |
| `dm meta anomaly add <type> <desc>` | 手动添加异常 |
| `dm meta correction add <target> <action>` | 手动添加修正 |
| `dm meta correction apply` | 批量应用修正 |
| `dm meta correction discard <id>` | 丢弃修正 |
| `dm meta queue` | 审核队列 |
| `dm meta queue process` | 处理队列 |

---

## 十一、关联链 (Association Funnel L1→L5)

| 命令 | 功能 |
|------|------|
| `dm association show` | 漏斗：L1-L5 各层计数 |
| `dm association layer <N>` | 查看某层所有关联 |
| `dm association promote <entity>` | 手动晋升 L(N→N+1) |
| `dm association demote <entity>` | 手动降级 |
| `dm association add <e1> <e2> <layer>` | 手动添加关联 |
| `dm association remove <e1> <e2>` | 删除关联 |
| `dm association search <keyword>` | 搜索关联 |
| `dm association path <e1> <e2>` | 两个实体间关联路径 |

---

## 十二、行为链 (Behavior)

| 命令 | 功能 |
|------|------|
| `dm behavior predict` | 预测下一行为 |
| `dm behavior show` | 行为图：edges + patterns |
| `dm behavior stats` | 统计 |
| `dm behavior edge show <from>→<to>` | 查看行为边 |
| `dm behavior edge add <from> <to>` | 添加行为边 |
| `dm behavior edge weight <from> <to> <w>` | 设置权重 |
| `dm behavior edge remove <from> <to>` | 删除行为边 |
| `dm behavior pattern <name>` | 查看模式 |
| `dm behavior pattern add <name> <from>→<to>...` | 添加模式 |

---

## 十三、工程链 (Engineering)

| 命令 | 功能 |
|------|------|
| `dm engineering constraint check` | 约束检查 |
| `dm engineering constraint add <type> <target> <spec>` | 添加约束 |
| `dm engineering constraint remove <id>` | 删除约束 |
| `dm engineering constraint list` | 所有约束 |
| `dm engineering propagate` | 变更传播 |
| `dm engineering impact <change>` | 影响分析 |

---

## 十四、画像 (Profile)

| 命令 | 功能 |
|------|------|
| `dm profile show` | OCEAN 10维 + MBTI + BFI |
| `dm profile dimension <name>` | 查看某一维 |
| `dm profile dimension set <name> <val>` | 手动设置维度值 |
| `dm profile mbti <type>` | 手动设置 MBTI |
| `dm profile bfi set <name> <val>` | 设置 BFI 维度 |
| `dm profile correction add <dim> <delta> <reason>` | 添加修正 |
| `dm profile correction list` | 修正列表 |
| `dm profile correction undo <id>` | 撤销修正 |
| `dm profile reset` | 重置 |
| `dm profile history` | OCEAN 随时间变化 |
| `dm profile export` | 导出完整画像 JSON |

---

## 十五、ABC 规则 (Rules)

| 命令 | 功能 |
|------|------|
| `dm rules show` | 所有规则 |
| `dm rules search <keyword>` | 搜索 |
| `dm rules get <id>` | 查看单条规则 |
| `dm rules add <A> <B> <C>` | 添加：前提→行为→后果 |
| `dm rules edit <id> <key=val>...` | 修改规则 |
| `dm rules remove <id>` | 删除 |
| `dm rules enable <id>` | 启用 |
| `dm rules disable <id>` | 停用 (不删除) |
| `dm rules stats` | 规则统计：总数/启用/触发次数 |
| `dm rules import <file>` | 从 JSON 文件导入 |

---

## 十六、观察池 (ObservationPool)

| 命令 | 功能 |
|------|------|
| `dm obs show` | 统计：total/by_domain/consumed |
| `dm obs domains` | 列出所有 domain |
| `dm obs domain <name>` | 查看某 domain 下 bundle |
| `dm obs get <bundle-id>` | 查看单个 bundle 详情 |
| `dm obs search <keyword>` | 搜索内容 |
| `dm obs mark <bundle-id>` | 标记为 consumed |
| `dm obs evict` | 清理过期 |
| `dm obs clear <domain>` | 清空 domain |
| `dm obs subscribers` | 当前订阅者 |

---

## 十七、知识图谱 (Knowledge)

| 命令 | 功能 |
|------|------|
| `dm knowledge show` | 对象数量 + 抽样 |
| `dm knowledge search <keyword>` | 搜索对象 |
| `dm knowledge get <name>` | 查看单个对象 |
| `dm knowledge object add <name> <type> <identity>` | 添加对象 |
| `dm knowledge object edit <name> <key=val>...` | 修改 |
| `dm knowledge object remove <name>` | 删除 |
| `dm knowledge relation add <a> <b> <type>` | 添加关系 |
| `dm knowledge relation remove <a> <b>` | 删除关系 |
| `dm knowledge export` | 导出完整 JSON |

---

## 十八、概念图 (Concepts)

| 命令 | 功能 |
|------|------|
| `dm concepts` | 所有概念 |
| `dm concepts search <keyword>` | 搜索 |
| `dm concepts add <name>` | 添加概念 |
| `dm concepts remove <name>` | 删除 |
| `dm concepts link <a> <b>` | 关联概念 |

---

## 十九、Mind (注意力/锚点/错误)

| 命令 | 功能 |
|------|------|
| `dm mind attention` | 当前注意锚点 |
| `dm mind attention add <name> <weight>` | 添加锚点 |
| `dm mind attention remove <name>` | 删除 |
| `dm mind mistakes` | 错误模式 |
| `dm mind mistakes add <pattern> <severity>` | 添加错误 |
| `dm mind mistakes resolve <id>` | 标记已解决 |
| `dm mind relation <entity>` | 实体关系 |
| `dm mind export` | 导出 mind 全部数据 |

---

## 二十、任务图 (TaskGraph)

| 命令 | 功能 |
|------|------|
| `dm task show` | 当前任务图 |
| `dm task node <id>` | 查看任务节点详情 |
| `dm task node add <name> [--deps=<id,id>]` | 添加任务 |
| `dm task node edit <id> <key=val>...` | 修改 (name/status/desc) |
| `dm task node remove <id>` | 删除 |
| `dm task node status <id> <val>` | 设置状态 |
| `dm task edge add <from> <to>` | 添加依赖 |
| `dm task edge remove <from> <to>` | 删除依赖 |
| `dm task save` | 持久化到文件 |
| `dm task confirm` | 标记确认 (注入下次对话) |
| `dm task import <file>` | 从 JSON 导入 |
| `dm task export <file>` | 导出到文件 |

---

## 二十一、应用层 (保留)

| 命令 | 说明 |
|------|------|
| `dm chat [--turns N]` | 交互对话 + 画像追踪 |
| `dm test [bench]` | benchmark |
| `dm ab` | A/B OCEAN 对比 |
| `dm monitor [--list]` | 会话日志 |
| `dm export [--format]` | 导出 |
| `dm config` | 配置 |
| `dm clean [--all]` | 重置 |

---

## 二十二、数据管理

| 命令 | 功能 |
|------|------|
| `dm data paths` | 所有数据文件路径/大小 |
| `dm data export <module>` | 模块数据导出 |
| `dm data import <module> <file>` | 模块数据导入 |
| `dm data backup` | 全量备份 (tar.gz) |
| `dm data restore <file>` | 从备份恢复 |
| `dm data reset` | 完全清空 (危险) |

---

## 二十三、全局

| 命令 | 功能 |
|------|------|
| `dm version` | CLI + 引擎版本 |
| `dm help [command]` | 帮助 |
| `dm help --all` | 列出所有命令 |

---

## 实现路径

| Phase | 内容 | 命令数 |
|-------|------|:-----:|
| P1 | engine + session + event send + reply + task | ~30 |
| P2 | discourse + pcr + intent + context | ~35 |
| P3 | blueprint + decider + meta | ~25 |
| P4 | association + behavior + engineering | ~25 |
| P5 | profile + rules + obs + knowledge + concepts + mind | ~45 |
| P6 | app layer 移植 + data 管理 | ~15 |
| **Total** | | **~175** |
