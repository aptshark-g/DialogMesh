# 压缩交接 — LLM 认知层专项 + 全局审计终态（2026-08-03）

> 压缩唯一恢复入口（本批）。恢复顺序: 本文档 → `GLOBAL_AUDIT_PLAN_20260803.md` →
> 各模块审计文档（见 §四）。
> 状态: **19 审计单元完成（18 业务链 + LLM 认知层专项）；剩余深度审计量已量化**。

---

## 一、本批新增（LLM 认知层专项，用户点名"思考树"）

```
新目录: docs/only/llm_cognitive/
  AUDIT_ENTRY_20260803.md       第一轮盘点（4 体系 19 文件 + 消费矩阵 + 测试实锤）
  DESIGN_FULL_READ_20260803.md  设计精读（6 篇文档，七节）

核心实锤（5 项）:
  1. LLM 间共享树通信全链路断——6 LLM 实例从不调用认知编译器/从不写树
     （llm_engine.py build_cog_node 定义未用，process() node_id=None）
  2. LLM Provider v3.0 升级全未落地——cognitive_mode/native_async/模式路由零实现；
     根级与 v3_0 双套 Provider 并存；139.5KB 零测试
  3. cognitive_tree CrossRef async 迁移 9 测试失败
  4. 根级 cognitive_compiler 4 文件孤儿（decomposer/injector/scorer/dual_manager）
  5. v6 主路径不消费认知层（tiered/ 活跃在对话树 A 路径 + runtime p3）
```

---

## 二、剩余深度审计量（量化）

### 1. 主题树 manager_v2 组件深读（挂上下文审计，1 个单元）
```
core/agent/topic_tree/  合计 ~72KB/8f
  manager_v2.py 44.8KB（巨文件核心，未深读）
  heat_model.py 6.4KB / models.py 6.1KB / context.py 4.6KB /
  manager.py 5.0KB / fact_store.py 3.7KB / compass_patch.py 1.2KB
已知: context_manager/discourse_manager.py 真消费 TopicTreeManagerV2 + EmbeddingEngine
```

### 2. 外围服务审计（P2 可选，~760KB/88f）
```
orchestrator/   144.5KB/9f（宿主, 蓝图审计触及 agent_native）
coordinator/     93.5KB/7f（bayesian/fusion/multi_tier_llm）
service/（两处） 248KB/26f（agent_service/api/session/rate_limiter/stores）
frontend/        77.2KB/6f（clarification/multimodal/taskgraph_viz/websocket）
world/           43.7KB/8f（TRACEABILITY"42L stub"已过时）
learning/        54.0KB/8f（蓝图消费）
memory/          45.8KB/6f（孤儿: xml_cards/federated_index 零引用）
observation/     52.2KB/20f（活跃, TRACEABILITY"闲置"已过时）
```

> 建议: 主题树先做（挂上下文）；外围服务按"与施工相关性"裁剪——
> observation/memory/learning 并入对应模块补充，orchestrator/coordinator/service/
> frontend/world 可暂缓（P2）。

---

## 三、剩余问题清单（全局待拍板池，压缩后讨论）

### 贯穿性系统问题（19 审计单元反复出现）
```
P-1  组件齐备、接线断裂（同型 × 5+）:
      _meta_consumer/_trace_v3 恒 None / LLMEngine→Compiler 从不调用 /
      planner models.py 重导出壳 / MetaSubscriber 从未订阅 / FeedbackBridge 恒空
      → 治理: 全局"接线审计"专项 or 施工时逐模块接
P-2  多代演进→分裂（同型 × 5+）:
      planner 07-21 曾 70% 实现→08-xx 回归 / PCR/行为链同型 /
      双套 Provider / 双套 EventBus / 双决策器 / v4 壳(3 处导入即炸)
      → 治理: 统一迁移纪律 + 断链检测（import 探针 CI）
P-3  测试缺失/断裂: llm_providers 零测试 / planner 20 失败 / cognitive_tree 9 失败 /
      浅断言"先射箭再画靶"
P-4  双路径分裂: A 路径（agent_native/bootstrap_v6）挂了 vs B 路径（runtime/cli）没挂
      → 治理: 路径归一拍板
```

### 待拍板点（按模块）
```
元认知: M5(写路径接线)/M8(三套归一)/M9(TriggerEngine 去留)
规划:   models.py 恢复(git 找回)/v4 skill_layer 壳清理/三套规划归一
持久化: 存储架构（SQLite 拓展/redis/FactStore 批量写）/
        ENGINEERING_PERSISTENCE 新增部分是否落地
执行层: X1(NATS 无限重连)/X2(on_event 递归)/X3(3 阶段 handler 缺失)/
        X4(handler 输出传递)/双决策器归一/B 路径挂载
LLM 认知层: 共享树通信接线(6 LLM→Compiler)/认知模式落地/双套 Provider 归一/
        v6 是否接入认知层
```

---

## 四、审计文档索引（本批 + 全部）

```
docs/only/GLOBAL_AUDIT_PLAN_20260803.md   全局计划（19 单元完成 + 核查 3 轮）
docs/only/meta/          AUDIT_ENTRY + DEEP_AUDIT + DESIGN_FULL_READ（11 篇设计）
docs/only/planner/       AUDIT_ENTRY + DEEP_AUDIT + DESIGN_FULL_READ（8 篇设计）
docs/only/persistence/   AUDIT_ENTRY + DEEP_AUDIT + DESIGN_FULL_READ（6 篇设计）
docs/only/execution/     AUDIT_ENTRY + DEEP_AUDIT + DESIGN_FULL_READ（8 篇设计）
docs/only/llm_cognitive/ AUDIT_ENTRY + DESIGN_FULL_READ（6 篇设计）
docs/only/wise/          PARADIGM（A1-A25/P1-P28 公约, 全局消解用）
```

---

## 五、压缩后恢复三步

```
1. 读本文档（终态 + 剩余量 + 拍板池）
2. 读 GLOBAL_AUDIT_PLAN_20260803.md（19 单元进度 + 三查结论）
3. 按需读模块文档（§四索引）→ 继续主题树深读 或 进入全局拍板讨论
```
