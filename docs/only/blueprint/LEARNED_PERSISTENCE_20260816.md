# 学习闭环持久化 — 施工记录（2026-08-16）

> 触发: 接线核查发现 `LEARNED_TEMPLATES` 纯内存 dict, 学到即丢（重启归零）
> —— "工作流自增长"核心卖点闭环断。全库探针: `learn_from_execution` 有
> 生产调用方, 蒸馏管道有实现, 但落盘缺失。

## 〇、核查结论

- `learn_blueprint`（SkillRegistry）: ✅ 有实现, 要求含 tool 节点才沉淀
- `distill_once`（LearningBridge）: ✅ 有实现, trace≥3 + A24 coverage 60-80%
- `LEARNED_TEMPLATES` 持久化: ❌ **无**（纯内存, 重启归零）
- 生产注入（v3_session_api → learn_from_execution）: ✅ 已接（GAP-D2）

→ 缺的只有"最后一公里": 学到的东西不落盘。

## 一、实施

### 1. BlueprintDAG 序列化（models.py）
- `to_dict()` / `from_dict()`: nodes/edges/strategy/confidence/design_rationale
  （dataclass 全字段, 含 params 深拷贝语义）。

### 2. LEARNED_TEMPLATES 持久化（skill_registry.py）
- 落盘 `data/learned_templates.json`（`DM_LEARNED_TEMPLATES_PATH` 可覆盖,
  测试隔离）; 原子写盘 tmp+replace。
- 模块导入时 `_load_learned_templates()` 恢复（A17 记录不丢）;
  `learn_blueprint` 成功后 `_persist_learned_templates()`。
- `skill_lifecycle` 裁剪（pop）后同步落盘, 保持一致性。

### 3. 二阶抽象验证（A24 可逆推）
- 现有 `LearningBridge._a24_verify`: coverage 60-80%（<60% 没学到,
  >80% 过拟合）——"伪二阶抽象 = 逆推验证"的既有判据, 本轮补测试固化。

## 二、测试（test_learned_persistence.py 6 项 + production_learning 隔离）

- DAG round-trip（字段全保留）
- learn → 落盘 → 模拟重启恢复 → `SkillRegistry.match` 命中 LEARNED 模板
- 无 tool 节点 DAG 不学习（不落盘）
- A24 三档: coverage 0.6 达标 / 0.4 不学 / 1.0 过拟合拒绝
- test_production_learning 加 autouse fixture 隔离落盘路径（防污染生产
  data/learned_templates.json）

## 三、验证

- 9/9 测试绿; 全量 2063 绿（见 FULL_RUN_QUANT_20260816.md）。

## 四、边界

- 落盘是整表 JSON（模板数小）; 模板量级上来后可改 JSONL/增量。
- LEARNED_TEMPLATES 与 SkillLifecycle 元数据（状态表）分离存储; 活性迁移
  仍由 lifecycle 管, 持久化只保 DAG 本体。
