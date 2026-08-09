# 意图模块级补全施工记录 — 2026-08-04

> 范围：模块级补全第二批（对话树 D 系列之后）——意图 I3-I12。
> 拍板依据：R1（三时相）/R2（类别种子集）/R3（按三时相落位）/R4（4 通道订阅矩阵）。
> 状态：✅ I3/I4/I5/I6/I8/I9 完成；I7 已有 T2 回写（engine `_apply_l3_feedback`）；
> I10 记录不施工（零调用方，边界纪律）；I11/I12 已由 R3 T0/T1 落位覆盖。

---

## 一、本轮完成项

### I3 — engine 主路径启用新包（T1 热路径）✅
```
runtime/engine.py:
  + _init_intent_runtime(): 懒初始化 Agent-Native 意图管线
    DualTrackIntentPipeline(llm=self._llm_provider, belief_acc=self._l2_5_belief)
  → handle_intent 首次调用时初始化；无 LLM 时 pipeline 内部显式降级
    （trace.degraded），不再静默跳过
```
`event/handlers.py handle_intent`：
- 优先走新包 `pipeline.process(text)`（is_multi/segments/confidence/source）
- 兼容旧 `parser.parse(user_input=text)` 契约（防御式）
- 无 parser 时 fallback "general"（保留，但新包接上后不再是主路径）

### I4 — 旧 8 阶段 shim 归档（registry 切新包）✅
```
cli/registry.py:285
  core.agent.v3_common.intent_parser:IntentParser（断链 shim = None）
  → core.agent.intent.dual_track:DualTrackIntentPipeline
实测: build_dialogmesh_registry().resolve_all() → intent_parser 加载
      DualTrackIntentPipeline 实例（不再 None）
```

### I8 — shim 引用方清理（mcp 生产路径）✅
```
mcp/server.py:
  IntentParser() 直接调用会崩（shim=None → TypeError 'NoneType' not callable）
  → _default_intent_parser(): 新包优先（DualTrackIntentPipeline）→
    旧 shim 次之 → 全失败显式 warning 日志 + None（诚实降级）
  → MCPServerLifespanContext.parser = DualTrackIntentPipeline ✅
  → 3 处 Optional[IntentParser] 注解改 Any
cognitive_tools._ensure_parser: 已显式 raise（R3 诚实降级，不动）
```

### I9 — 测试补全 ✅（新增 11 项）
```
intent/tests/test_fusion_ambiguity.py（新增）:
  FusionDecider 三策略（vote_consensus / weighted_mix / llm_adjudicate）
  + PCR 调控（complexity>0.8 强制 LLM / noise>0.7 加权 literal×1.5、
    discourse×0.7）
  + AmbiguityGate 5 触发器（pass/auto_resolve/llm_resolve/ask_user 升级）
  + PCR noise 推高 score 升级路径
```

### I5/I6 — 5 链验证 + PCR 调控（既有，本轮验证）✅
- `multi_intent_splitter` 已接 5 链验证（literal/profile/association/
  discourse/engineering）+ FusionDecider + AmbiguityGate（R3 已施工）
- splitter 传入 `pcr_zone` → complexity/noise 调控（I6 落地）
- `multi_perspective` 被 dual_track 冷路径消费（非孤儿）✅

### I7 — 意图↔对话树/画像接口（T2 回写既有）✅
- engine `_apply_l3_feedback`：tree_annotation{topic,action} → 对话树
  primary_intent 通道 + profile_update → 画像（R4 ① 已落地）
- `_last_intent` 现由 handle_intent 新包写入（category/segments/confidence）

---

## 二、验证数字

```
intent 全量:      19/19 ✅（splitter 8 + 新增 fusion/ambiguity 11）
statemachine M4:  10/10 ✅
CLI 28 + kernel 49: 77/77 ✅（engine 换新包意图管线后无破坏）
MCP 26/26 ✅（anaconda3，HAS_MCP=False 防御路径）
```

## 三、环境（本轮新增）

```
mcp 包已安装: .venv（Python 3.13）mcp 1.29.0 + fastmcp 3.4.5
  - anaconda3 3.9 无法装 mcp（官方要求 ≥3.10）→ MCP Server 在 .venv 跑
  - .venv 无 pytest → MCP 测试仍在 anaconda3 跑（HAS_MCP=False 路径）
  - 已验证: .venv 下 mcp/server HAS_MCP=True + create_mcp_server() OK
```

## 四、剩余（记录不施工 / 待后续）

```
I10  自适应阈值两套归一（v3_common GP+MLP 632L vs coordinator Bayesian）
     → 零调用方，边界纪律记录不施工；engine 只用 gates 简单 EMA
I11  多意图拆分验证 — 已由 R3 5 链验证覆盖（规则为主→LLM 裁决）
I12  认知双工形态 — 已由 R1 T0/T1 落位（规则边界 + LLM 主执行）
意图↔对话树 ②话题切换信号/③域选择 通道: 接口已定义，接线未做
     （D12 get_domain_C 归子图施工；话题切换归对话树 D 系列后续）
```

## 五、改动文件清单

```
core/agent/runtime/engine.py               _init_intent_runtime（I3）
core/agent/event/handlers.py               handle_intent 新包优先（I3）
core/agent/cli/registry.py                 intent_parser 注册切新包（I4）
core/agent/mcp/server.py                   parser 初始化防御（I8）
core/agent/intent/tests/test_fusion_ambiguity.py  新增 11 项（I9）
```

## 六、与审计对照（IMPLEMENTATION_AUDIT §八）

- 内核选型：新包 + L3 协同 ✅（engine 意图 = DualTrackIntentPipeline 热路径
  + L3 MultiPerspectiveValidator 验证 + T2 回写，非孤岛）
- registry 断链：intent_rule_registry 由新包替代（不再依赖旧 8 阶段）✅
- shim 清理：11 引用方中生产路径（mcp）已防御；测试引用保留（历史资产）✅
- 意图↔对话树 4 接口：① primary_intent（L3 tree_annotation）✅
  ④ compass intent_novelty（engine 已注入）✅；②③ 接口定义待接线
