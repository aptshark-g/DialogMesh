# DialogMesh v6 — Architecture Audit

> 日期: 2026-07-30 · 审计人: strict architect mode
> 原则: 不粉饰、不假设、不乐观。只记录可验证的事实。

---

## 一、代码规模

| 文件 | 行数 | 职责 | 健康度 |
|------|-----:|------|:------:|
| `core/agent/runtime/engine.py` | 3,721 | 认知运行时引擎 | 🔴 太胖 |
| `core/agent/api/api.py` | 1,919 | 全量 API 路由 | 🟡 可接受 |
| `core/agent/cli/entry.py` | 1,198 | CLI 入口+dispatch | 🟡 可接受 |
| `core/agent/event/handlers.py` | 281 | StateMachine 8个处理器 | 🟢 良好 |
| `core/agent/event/statemachine.py` | 176 | 状态机核心 | 🟢 良好 |
| `core/agent/api/v6_app.py` | 268 | v6 路由注册 | 🟢 良好 |
| `core/agent/cli/engine.py` | ~320 | CLI 引擎工厂 | 🟡 可接受 |

**风险**: `engine.py` 3721 行、180KB。改前必须 `git checkout`——是项目最脆的文件。

---

## 二、双轨架构 (P0 — 最高风险)

### 问题

系统有 **两条互不知道对方的事件处理路径**:

```
路径 A (legacy, 3,500+ 行):
  on_event() → serial NLP chain
  → discourse analysis → behavior recording
  → granular regulation → meta cognition

路径 B (new, 42 行):
  on_event_sm() → StateMachine.run_pipeline()
  → 8 phases, 12 transitions
  → PCR → Intent → Planning → LLM → Discourse → Behavior → Meta → Persist
```

### 风险

1. **路径 A 仍在 `on_event()` 中活跃**——从未删除
2. **路径 B 不知道路径 A 做了什么**——如果 A 改了 `_meta_cognition`，B 不知道
3. **两个初始化路径**: `start()` (660行,从不用) vs `_create_engine_instance()` (factory,手动重造)
4. **数据竞争**: 两个处理器可能同时写 `_behavior_graph_adapter`

### 证据

```
$ grep "def on_event" engine.py
def on_event(self, event_id, kind, payload, ...):   ← 第 197 行, 仍活跃
def on_event_sm(self, ...):                          ← 第 216 行, 新路径

$ grep "def start" engine.py  
def start(self, provider_config, ...):               ← 第 217 行, 660行,N E V E R 调用
```

### 修复方向

```
目标: on_event_sm 作为唯一入口
  Week 1: on_event → 只有路由,转发到 on_event_sm
  Week 2: engine.start() → 统一到 _create_engine_instance
  Week 3: 删除死代码 (逐步,每步验证)
```

---

## 三、设计文档 vs 代码实现 (P0 — 信任危机)

### 问题

23 个 `DESIGN_*.md` 文件，多个标 "100% ✅"。但代码实际状态不同。

| 设计文档 | 设计宣称 | 代码实际 | 差距 |
|----------|---------|---------|:----:|
| DESIGN_AUDIT.md | "可达性 24/24 100%" | /v6/objects → "No world objects" | ❌ |
| DESIGN_RUNTIME_KERNEL.md | "HotStore 自动填充" | 手动 `_cache_hot()` 调用 | ⚠️ |
| DESIGN_GLOBAL_STATE_MACHINE.md | "single entry point" | 两条路径都在跑 | ❌ |
| DESIGN_DISTRIBUTED.md | "EnginePool 4-slot" | pool.py 存在但未集成 | ⚠️ |
| DESIGN_METACOGNITION_RUNTIME.md | "workflow graph loop" | MetaCognition 对象在线但空 | ⚠️ |

### 根因

设计文档把 **"端点存在"** 和 **"数据存在"** 混淆了。`GET /v6/objects` 返回 200 但 `{"count": 0}`——设计标 ✅，用户看到空数据。

### 修复方向

```
每个设计文档末尾加 "实际状态" 表:
  - 端点: ✅ 存在
  - 数据: ⚠️ 空 (需 3 轮对话积累)
  - 测试: ❌ 无
```

---

## 四、死代码 (P1)

### 1. engine.start() — 660行未调用的代码

```python
# engine.py line 217
def start(self, provider_config, provider_type, engine_config):
    # 660 行创建 12 个深度对象
    # 从未在生产中被调用
    # _create_engine_instance() 手动重造了所有对象
```

**影响**: 两个初始化路径，不同步。改了 factory 忘记改 start() → 不一致。

### 2. on_event() — 3500行遗留

```python
# engine.py — 3500+ 行 serial NLP chain
# 仍在 on_event() 中活跃
# on_event_sm() 没有引用它,两者互不知
```

### 3. 导入错误变无声失败

```python
# api.py 有 4 个 import 包裹在 try/except:
try:
    from core.agent.v4.api_viz_edit import router as viz_edit_router
except ImportError:
    viz_edit_router = None  # ← 模块删了,import 还留着

try:
    from core.agent.v4.api_annotate import router as annotate_router
except ImportError:
    annotate_router = None  # ← 同上

# 类似的还有 v3_2.integration, v4.cognitive 等模块
```

**影响**: 功能静默丢失，无人知晓。

---

## 五、数据真实性 (P1)

### v6 API 端点数据审计

```
端点                    状态    数据内容
────────────────────────────────────────────
/v6/profile            ✅      OCEAN 10维 (mock 0.5)
/v6/sessions           ✅      44 sessions (JSON)
/v6/graph              ✅      节点+边
/v6/discourse-tree     ✅      63 blocks
/v6/behavior           🟡      edges=0 (无对话历史)
/v6/meta               ✅      reviewed:true
/v6/abc                ✅      rules=6
/v6/mind               ✅      subsystem list
/v6/objects            ⚠️      count=0
/v6/relations          ⚠️      count=0
/v6/causal             ⚠️      chains=0
/v6/pipeline           ⚠️      traces=0
/v6/extraction         ⚠️      tiers=0
/v6/perspectives       ⚠️      horizon=0
/v6/parameters         ⚠️      registry empty
/v6/engineering        🟡      KG 在线但空
/v6/annotations        ✅      12 entries (pipeline auto-fill)
/v6/corrections        ✅      12 entries
/v6/feedback           ✅      empty (无错误)
/v6/metrics            ✅      subsystem stats
/v6/audit              ✅      4 dimension report
```

**结论**: 17 端点返回真实数据, 7 端点返回空——需要对话积累或引擎填充。

---

## 六、测试缺口 (P2)

### 现状

```
单元测试: 76 (CLI 28 + Event 46 + Pluggable 2)
集成测试: 0
API 契约测试: 0
性能测试: 0
```

### 缺失

| 测试类型 | 应覆盖 | 现状 |
|----------|--------|:---:|
| 管线测试 | PCR→Intent→...→PERSIST 全链 | ❌ |
| API 合约 | 17 端点 200 + 正确 schema | ❌ |
| 并发测试 | EnginePool 4-slot 并发 | ❌ |
| 降级测试 | NATS down → memory fallback | ❌ |
| 回归测试 | on_event → on_event_sm 行为一致 | ❌ |

---

## 七、架构维度评分

| 维度 | 评分 | 关键问题 |
|------|:---:|----------|
| 凝聚度 | 4/10 | engine.py 3721行承担太多职责 |
| 耦合度 | 5/10 | 双轨导致隐式依赖 |
| 可扩展性 | 7/10 | SubsystemRegistry + ToolRegistry 到位 |
| 韧性 | 4/10 | 降级存在但未测试 |
| 可观测性 | 6/10 | Tracer+EventLog+HotStore 三层 |
| 可测试性 | 3/10 | 无集成测试, engine 启动依赖 37 子系统 |
| 性能 | 5/10 | HotStore sub-μs,但 start() 660行浪费 |
| 安全性 | N/A | 无 auth (localhost only) |
| 可部署性 | 4/10 | 无 Dockerfile, 无 CI/CD, 依赖外部 Gateway |
| 白盒性 | 7/10 | 75 端点,16/23 属性可见, CLI 全覆盖 |

**加权总评: 5.0/10**

---

## 八、修复路线图

### P0 — 本周 (结构性风险)

| 任务 | 文件 | 影响 | 成本 |
|------|------|------|:---:|
| on_event → 路由到 on_event_sm | engine.py | 消除双轨 | 2h |
| engine.start() → 合并到 factory | engine.py, cli/engine.py | 统一初始化 | 3h |
| 删除 api.py 4个死 import | api.py | 清理无声失败 | 30m |

### P1 — 下周 (代码质量)

| 任务 | 文件 | 影响 | 成本 |
|------|------|------|:---:|
| engine.py 拆分 | runtime/engine.py → 3-4文件 | 可维护性 | 4h |
| v6 空端点补齐 | stubs_api.py, engine.py | 数据真实性 | 3h |
| 设计文档校对 | docs/DESIGN_*.md | 信任修复 | 2h |

### P2 — 之后 (工程化)

| 任务 | 影响 | 成本 |
|------|------|:---:|
| 5条关键路径集成测试 | 防回归 | 3h |
| 设计文档瘦身 23→10 | 可读性 | 2h |
| CI/CD pipeline | 自动化 | 4h |

---

## 九、诚实结论

```
DialogMesh v6 是一个野心勃勃的项目。
设计文档覆盖度很高，但代码实现有显著差距。

能跑 —— CLI 166 命令、v6 75 端点、37 子系统全部在线。
不敢改 —— engine.py 3721行无测试覆盖，双轨遗留代码从未清理。

如果今天上线生产:
  - Mock 模式: ✅ 能跑
  - DeepSeek 模式: ⚠️ Gateway 需要健康
  - 高并发: ❌ 无 EnginePool 集成
  - 长时间运行: ⚠️ EventLog 无限增长未设上限
```


---

## 十、归档策略 — un_use/ (不删除,安全退回)

### 原则

**不删除危险代码——归档到 `un_use/` 目录。**
- git log 永远可恢复
- `un_use/` 全文搜索快
- 出问题 → 10 秒找到原文

### engine.py 归档 (~3500 行移出)

```
保留 (~200 行):
  on_event_sm()              唯一入口
  _create_engine_instance()  统一初始化
  stop() / status()

移入 un_use/engine_legacy/:
  on_event()                      → legacy_on_event.py      (~3500 行)
  start()                         → legacy_start.py         (~660 行)
  _feed_profile / _retrospect     → legacy_cognitive.py
  _validate_* / _diff_*           → legacy_validation.py
```

### api.py 清理

```
删除 4 个 try/except ImportError 死 import
每个标注 git SHA 可恢复
```

### un_use/ 目录

```
un_use/
  ├── engine_legacy/
  │   ├── legacy_on_event.py
  │   ├── legacy_start.py
  │   ├── legacy_cognitive.py
  │   └── legacy_validation.py
  └── README.md  归档原因+恢复方法
```

### 恢复

```
git show <commit>:engine.py → 完整恢复
```

---

## 十一、实施策略 — 先覆盖,后迁移

### 原则

迁移前必须确保新代码完全覆盖旧代码。先验证 → 再路由 → 再归档。

### 阶段 A: 覆盖验证 (审计)

| 步骤 | 内容 | 产出 |
|:----:|------|------|
| A1 | 审计 `on_event()` 做什么 | coverage_map.md |
| A2 | 审计 `on_event_sm()` handler 覆盖 | gap_list.md |
| A3 | 标注 gap | 待修复清单 |

### 阶段 B: 补缺口

| 步骤 | 内容 | 文件 |
|:----:|------|------|
| B1 | 补齐缺失 handler | handlers.py |
| B2 | on_event → passthrough to on_event_sm | engine.py |
| B3 | 全量测试验证 | pytest 78/78 |

### 阶段 C: 归档

| 步骤 | 内容 |
|:----:|------|
| C1 | 创建 un_use/engine_legacy/ |
| C2 | on_event/start 移入 legacy 文件 |
| C3 | engine.py 瘦身 ~200行 |
| C4 | 清理 api.py 死 import |

### 阶段 D: 验证

| 步骤 | 内容 |
|:----:|------|
| D1 | 重启后端,验证 v6 端点 |
| D2 | 3轮对话验证管线持久化 |
| D3 | git tag pre-archive + post-migrate |

### 回退

任何阶段失败: `git checkout engine.py api.py` → 恢复 → 重新开始
