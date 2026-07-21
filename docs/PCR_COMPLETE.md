# PCR (Pre-Cognitive Router) — 完整整理

> 2026-07-21 · 来源: 设计文档 + 代码审计

---

## 一、PCR 是什么

DialogMesh 的**输入层网关**。在所有认知处理之前，对用户消息做"第一眼判断"：

```
用户输入 → PCR → {期望类型, 噪声度, 复杂度, 认知画像, 策略} → 下游 (IntentParser → Engine)
```

类比：PCR 是安检门——还没进门就知道你是来问路还是来找茬。

---

## 二、PCR 处理的 5 个信号

```
输入: PCRInput_v1 {user_text, history[], conversation_id}
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
── 1.期望识别 ── 2.噪声评估 ── 3.复杂度评估 ──
    │               │               │
    ▼               ▼               ▼
── TOOL/ADVISOR/  0.0-1.0        0.0-1.0
   COMPANION/      (垃圾/低质)   (单步→多步)
   UNKNOWN
                    │
    ┌───────────────▼───────────────┐
    ▼               ▼               ▼
── 4.认知画像 ──── 5.策略推导 ──── 输出 ──→
    │               │
    ▼               ▼
  CognitiveLevel  execution_mode: FAST_EXECUTE/CLARIFICATION/
  ExpertiseLevel  DEEP_RESEARCH/CONVERSATIONAL/BALANCED
  PreferredDetail prompt_style: BRIEF/EXPLANATORY/TUTORIAL/BALANCED
  CognitiveTraits ambiguity_strategy: AGGRESSIVE_AUTO/CONSERVATIVE_ASK/BALANCED
```

---

## 三、数据契约

### PCRInput_v1
```python
user_text: str              # 当前用户输入
history: List[HistoryEntry] # 历史对话 (可选)
conversation_id: str         # 会话ID (可选)
metadata: Dict               # 扩展字段
```

### PCROutput_v1
```python
# ── 核心评估 ──
expectation: str            # TOOL / ADVISOR / COMPANION / UNKNOWN
noise_level: float          # 0-1 噪声度
complexity_level: float     # 0-1 复杂度
cognitive_profile: CognitiveProfile_v1

# ── 派生策略 ──
execution_mode: str         # FAST_EXECUTE / CLARIFICATION / DEEP_RESEARCH / CONVERSATIONAL / BALANCED
parser_config_overrides: dict  # 下传给 IntentParser 的配置覆盖
prompt_style: str           # BRIEF / EXPLANATORY / TUTORIAL / BALANCED
ambiguity_strategy: str     # AGGRESSIVE_AUTO / CONSERVATIVE_ASK / BALANCED

# ── 建议 ──
suggested_next_actions: List[str]  # 前端渲染为快捷按钮
should_attach_process: bool        # 提示附加进程
should_refresh_analysis: bool      # 提示刷新分析

# ── 遥测 ──
trace_log: List[str]
latency_ms: float
implementation: str                # 哪个实现: "rule_based" / "llm_enhanced" / "hybrid"
```

---

## 四、接口 (IPCRRouter)

```python
class IPCRRouter(ABC):
    name: str                          # 实现名称
    version: str                       # 版本号
    
    def warm_up(self) -> None
    def shutdown(self) -> None
    def reload_config(self, config: Dict) -> None
    def evaluate(self, input: PCRInput_v1) -> PCROutput_v1  # ← 核心方法
    def get_health(self) -> PCRHealthStatus
    def get_telemetry(self) -> TelemetryReport
    def get_capabilities(self) -> List[str]
    def get_schema(self) -> Dict
```

3 种实现：
- `RuleBasedPCR` — 规则引擎 (✅ 已实现)
- `LLMEnhancedPCR` — LLM few-shot (❌ 未实现)
- `HybridPCR` — 规则+LLM投票 (❌ 未实现)

---

## 五、RuleBasedPCR Pipeline (5 阶段)

```python
def evaluate(input):
    '''
    Stage 1: 期望识别 (ExpectationIdentifier)
        ├─ 关键词模式 → TOOL/ADVISOR/COMPANION
        ├─ 历史意图修正
        └─ LLM fallback (预留, 未启用)
    
    Stage 2: 噪声评估 (NoiseEstimator)
        ├─ 垃圾/广告比例
        ├─ 可理解性评分
        └─ 0-1 分数
    
    Stage 3: 复杂度评估 (ComplexityEstimator)
        ├─ 输入长度
        ├─ 实体密度
        ├─ 嵌套句结构
        ├─ 问题嵌套深度
        ├─ 多意图数量
        └─ 0-1 分数
    
    Stage 4: 认知画像 (CognitiveProfiler)
        ├─ cognitive_level
        ├─ expertise_level
        ├─ preferred_detail
        └─ cognitive_traits
    
    Stage 5: 策略推导 (StrategyDeriver)
        ├─ 期望 × 复杂度 × 噪声 → execution_mode
        └─ → prompt_style, ambiguity_strategy
    '''
```

---

## 六、代码清单

```
core/agent/pcr/
├── __init__.py              # 包导出
├── interface.py             # IPCRRouter 抽象基类 (204行)
├── datacontract.py          # PCRInput_v1 / PCROutput_v1 / CognitiveProfile_v1 (528行)
├── rule_based.py            # RuleBasedPCR 5阶段实现 (867行)
├── registry.py              # 显式注册 + 工厂 + 自动发现 (228行)
├── lifecycle.py             # 初始化→预热→回退→health→热加载→关闭 (304行)
├── config.py                # YAML/JSON 加载 + 环境变量 + 热加载 (229行)
├── fallback.py              # conservative/degraded/pass_through 策略 + 重试 (256行)
├── telemetry.py             # 滑动窗口 + p50/p99 + 错误率 (119行)
├── tests/
│   ├── test_datacontract.py    # 54 PASS
│   ├── test_rule_based.py      # 84 PASS
│   ├── test_integration.py     # 30 PASS
│   ├── mock_pcr.py             # 4种Mock (368行)
│   ├── adversarial_suite.py    # 6类对抗测试 (299行)
│   └── benchmark.py            # 性能基准 (289行)

总计: ~3500 行代码 + ~1000 行测试
```

---

## 七、当前接入状态

```
✅ PCR 代码: 全部存在 (9 模块)
✅ PCR 测试: 168/170 PASS
❌ PCR 接入 Engine: 完全缺失
❌ PCR 接入 API: 完全缺失
```

### 缺失的关键集成点

1. **`on_event` 开头应调用 `PCR.evaluate()`**
   ```python
   def on_event(self, event):
       pcr_input = PCRInput_v1(user_text=event.payload["text"])
       pcr_output = self._pcr_router.evaluate(pcr_input)
       # 用 pcr_output.noise_level 决定是否跳过
       # 用 pcr_output.execution_mode 决定策略
       # 用 pcr_output.prompt_style 调整 LLM 指令
   ```

2. **V3/V4 API 应传入 PCR 结果给前端**
   ```python
   # POST /v3/session/{id}/message 返回
   {
     "content": "...",
     "pcr": {
       "expectation": "ADVISOR",
       "noise": 0.1,
       "execution_mode": "DEEP_RESEARCH"
     }
   }
   ```

3. **`_compile_context` 应接收 PCR 策略**
   ```python
   def _compile_context(self, event, pcr_output):
       if pcr_output.execution_mode == "FAST_EXECUTE":
           # 跳过 DomainSelector, 直接快速上下文
       elif pcr_output.execution_mode == "DEEP_RESEARCH":
           # 调用 SubgraphCompiler 展开全图
   ```

4. **`_call_llm` 应使用 PCR prompt_style**
   ```python
   def _call_llm(self, event, pcr_output):
       if pcr_output.prompt_style == "BRIEF":
           system = "Be concise. One paragraph max."
       elif pcr_output.prompt_style == "TUTORIAL":
           system = "Explain step by step with examples."
   ```

---

## 八、预认知 (Pre-Cognitive) 的关键决策

PCR 的一个关键设计决策：**PCR 在 Engine 之前运行，不在 Engine 内部**。理由：

1. **隔离关注点**: 认知评估（你是谁、你要什么）≠ 认知处理（怎么回答你）
2. **快速判定**: 规则路径 < 10ms，可在并发线程中运行
3. **独立回退**: PCR 失败时可以安全降级为"平衡模式"而不影响 Engine

---

## 九、接入计划

```
Phase 1 (P0): 接入 on_event
    ├─ RuleBasedPCR 实例化 + warm_up
    ├─ on_event 开头调用 PCR.evaluate()
    └─ noise > 0.8 → 优雅拒绝

Phase 2 (P1): 策略联动
    ├─ execution_mode → 控制 _compile_context 深度
    ├─ prompt_style → 控制 _call_llm 系统指令
    └─ expectation → 控制 DomainSelector 权重

Phase 3 (P2): 前端联动
    ├─ PCR 结果随 V3 message 返回
    └─ 前端显示期望/噪声/策略标签
```
