# 施工记录 — 二阶抽象提炼管道（Heuristic Distillation）

> 日期: 2026-08-07 | 状态: 完成 ✅（P0 管道落地）
> 设计: HEURISTIC_DISTILLATION_DESIGN_20260806.md（含种子理论）
> 关联: blog chapter3（二阶抽象）/ A24 / GAP-D6 / CHAPTER3_VS_IMPL_ASSESSMENT

---

## 一、实现内容

### 1. heuristic_inventory.py（启发库存）
- `Heuristic` 数据类 — 四元组链（pattern_desc/conditions/counterexample/
  reasoning_path）+ belief（coverage/support/insight_score/source/active）
- `SEED_HEURISTICS` — 示范种子 ×2（**用户主导深化**, 非公理清单）:
  ① 差异即信息（比较是起源 → 无参照无意义 → 内禀也是参照 →
     统一化相对化）② 共性边界即分类（参考维度 → 排中律 → 集合操作 →
     锚定形式科学约束空间）
- `STRUCTURE_TEMPLATE` — 认知结构模板（现象→起源→边界→操作化）,
  即提炼管道输出规范
- `HeuristicInventory` — 存储/检索（词元重叠+洞察加权）/注入格式化
  （`[决策依据]` 块, 与 engineering 约束并列）/持久化（data/heuristics.json）/
  种子冷启动

### 2. heuristic_distiller.py（提炼管道, 变化驱动）
- `try_distill(reason, samples, variant)` — 触发入口
- **发散变体家族**（远迁移文献基础）: commonalize（结构对齐, Gentner）/
  forward_mask（前向掩盖）/ reverse_mask（反向掩盖）/ far_transfer
  （跨情境映射 + 显式结构线索, Gick & Holyoak）— LLM temp=0.8 调先验
- **收敛** — 暴露全上下文 temp=0.1 筛选 + 拒绝理由（知识边界）+
  insight_score（Holyoak & Thagard 三约束精神）
- **反事实扩展** — 低 coverage 高 insight（>=0.7）→ 构造"若启发为真→
  哪些行为该变"→ 样本中找证据连接 → 更新 reasoning_path
- **反推验证** — LLM 采样 20 条历史决策 → 启发能否解释 → coverage
  60-80% 合格; >80% 过拟合拒绝; <60% 幻觉拒绝
- **规则兜底** — 无 LLM 时相同工具序列计数（source="rule", 冷启动）
- 结构化输出: GenerateRequest(response_format="json" + json_schema)

### 3. learning_bridge 接线（变化触发）
- `attach_distiller(distiller)` — 挂载
- `trigger_distill(reason, variant)` — 统一触发
- `on_tool_failure(tool, error)` — 失败信号 → reverse_mask 发散
- `on_user_correction(dimension)` — 用户纠正信号 → commonalize 发散

### 4. 生产接入（2026-08-07 补齐, 闭环核心价值）

**engine.py** — learning_bridge 初始化处挂载二阶抽象:
- 创建 `HeuristicInventory`（engine._heuristic_inventory）+
  `HeuristicDistiller`（llm_provider=engine._llm_provider,
  trace_store=lb.trace_store）→ `lb.attach_distiller(dist)`

**executor.py** — 决策上下文注入 + 变化触发:
- `__init__` 加 `heuristic_inventory` / `learning_bridge` 参数
  （默认 None, 不破坏现有）; `_lazy_inventory()` / `_lazy_learning_bridge()`
  懒拿（构造注入优先, 其次 engine）
- `_handle_llm_reply`（mode=llm）: 注入 `format_for_prompt(query=text)`
  → `[决策依据]` 块拼进 user 消息（与 engineering 约束并列, A19 白盒）
- `_record_tool_step` 失败时: `lb.on_tool_failure(tool, error)`
  （节流: 累计 ≥2 次失败 且 间隔 ≥60s 才触发 LLM 蒸馏）

**kernel/dispatch.py** — 用户纠正触发:
- `kernel_behavior_feedback` 成功 mark_correction 后 →
  `engine._learning_bridge.on_user_correction("behavior")`

### 5. 白盒视图（2026-08-07, A19）

**kernel dispatch**: `kernel_heuristics_list()` — 库存全量 + 统计

**CLI（dm 命令）**:
- `dm heu list` — 库存全量（含统计）
- `dm heu stats` — 统计（total/active/by_source/avg_coverage/avg_insight）
- `dm heu show --id xxx` — 单条四元组详情
- `dm heu inject-test --query xxx` — 预览注入决策上下文的启发块

**API**: `GET /v6/heuristics`（列表 + 统计）

**前端 RightDock**: 新增「启发」tab（Lightbulb）—
`HeuristicsDockContent`: 统计卡（库存/平均覆盖率）+ 启发列表
（details 折叠: 现象/适用/反例/路径 + 来源/覆盖率/活跃标记）

## 二、验证

- 启发套件 **15/15 全绿**: inventory 5 + distiller 5 + 集成 5
  （llm_reply 注入/无库存不注入/失败节流触发/间隔节流/用户纠正触发）
- 白盒视图: kernel_heuristics_list 测试 1 + 回归 **65/65 全绿**
  （inventory+distiller+integration 16 + kernel_dispatch 49）
- 前端: tsc 归零 + vite build 成功（2.36s）

## 三、对齐哲学（用户深化确认）

- **种子 ≠ 公理清单**: wise 公理是项目内提炼产物（目标形态）, 当种子会
  自我印证闭环; 种子 = 认知结构模板 + 示范 few-shot + 质量判据
- **质量判据**: 锚定形式科学约束空间（排中律/映射形态/概率公理）→
  底层性 = 可迁移性 = 过时风险低
- **触发 = 变化驱动**（失败/用户纠正/公理冲突/活性/缺公理感）,
  定时蒸馏仅兜底
- **启发 = 决策依据, 与约束同构** — 注入上下文出现在所有决策处
- **反推原料 = 全模块**（执行轨迹/行为链/对话树/意图/wise）

## 四、遗留/后续

- ✅ 生产注入点已接: executor llm_reply 注入 + engine 挂载
- ✅ 生产触发已接: 工具失败（节流）+ 用户纠正
- **LLM 反推验证成本**: 每候选 1 次 LLM 调用（20 样本）— 可采样降为 10
  或分批
- **启发活性监测**（P2）: 定期检查 coverage 跌破阈值 → deactivate +
  再触发
- **CLI/API 视图**（P2）: dm heuristic list/inject 命令 + /v6/heuristics 端点
  ✅ 已实现（2026-08-07）— dm heu list/stats/show/inject-test + /v6/heuristics
  + RightDock「启发」tab
