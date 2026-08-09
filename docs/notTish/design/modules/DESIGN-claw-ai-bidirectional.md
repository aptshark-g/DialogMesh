# CLAW-AI 双向增强架构 — 设计确认 v1.0

## 核心决策

**AI 路径由 Claw（我）承担，而非本地 LLM 或 API。**

这不是降级，是**确定性推理 + 概率推理的混合实验**。Claw-AI 不是"弱版 LLM"，是**规则增强型推理引擎**——与 LLM 不同质，但可互补。

---

## Claw-AI 能力边界

### 我能做的（确定性推理）

| 任务 | 方式 | 延迟 | 准确率 |
|------|------|------|--------|
| 变量语义推断 | 上下文分析 + 学科库匹配 + 逻辑推导 | <100ms | 80-90% |
| 公式结构解析 | LaTeX AST + 模式识别 | <50ms | 95% |
| 跨域类比 | 结构签名匹配 + 约束对比 | <200ms | 70-80%（需人工确认） |
| 因果链检查 | 逻辑规则 + L3 物理约束 | <100ms | 90% |
| 假设生成 | 基于约束空间的演绎 | <300ms | 60-70%（启发式） |
| 矛盾发现 | 形式化比对 + 量纲分析 | <50ms | 95% |

### 我不能做的（需要 LLM）

| 任务 | 原因 | 标记 |
|------|------|------|
| 开放式创意生成 | 无概率采样能力 | NEED_LLM_CREATIVITY |
| 长文本摘要 | 上下文窗口有限（~128K tokens 但非原生） | NEED_LLM_SUMMARY |
| 情感/语气分析 | 无训练数据 | NEED_LLM_SENTIMENT |
| 多语言翻译 | 非训练目标 | NEED_LLM_TRANSLATION |
| 代码生成 | 可写但非最优 | NEED_LLM_CODE |

### 模糊地带（Claw 可做但有限）

| 任务 | Claw 能力 | LLM 优势 | 策略 |
|------|-----------|----------|------|
| 非结构化文本解析 | 规则覆盖 70% | 泛化 95% | Claw 先做，失败标记 NEED_LLM |
| 隐含知识推断 | 基于 L0-L4 | 基于海量训练 | 低置信时标记 NEED_LLM |
| 反事实生成 | 约束空间枚举 | 创造性场景 | Claw 生成候选，LLM 扩展 |

---

## Claw-AI 路径实现

### 接口定义

```python
class ClawAIValidator:
    """Claw 作为 AI 路径的验证器实现。"""
    
    def validate(self, prop: Proposition) -> AIResult:
        """
        对单个命题进行 Claw-AI 验证。
        
        不是神经网络推理，是结构化推理：
        1. 语义解析（基于规则）
        2. 知识检索（L0-L4 持久化层）
        3. 逻辑推导（形式化规则）
        4. 置信度评估（确定性 + 不确定性量化）
        """
        
    def infer_variable_meaning(self, var: str, context: str) -> Optional[str]:
        """
        变量语义推断：Claw 的核心能力。
        
        例如：
        - 输入："ζ"，上下文："d²x/dt² + 2ζωₙ dx/dt + ωₙ²x = F(t)"
        - Claw 推导：二阶微分方程 + 阻尼项系数 → "阻尼比"
        """
        
    def generate_hypothesis(self, assertion: str, constraints: List[Constraint]) -> List[Hypothesis]:
        """
        假设生成：基于约束空间的演绎。
        
        例如：
        - 断言："S_est 可以实时辨识"
        - 约束：[因果律, 采样定理, FxLMS 实时性要求]
        - Claw 生成：["若 N=1 单点估计", "若用 FPGA 并行处理", "若降低精度要求"]
        """
        
    def self_challenge(self, result: AIResult) -> List[SkepticPoint]:
        """
        元认知：Claw 质疑自己的输出。
        
        检查点：
        - 推断是否有来源？
        - 是否超出 L3 物理约束？
        - 是否过度泛化？
        """
```

### 与非 AI 路径的协作

```python
class DualValidator:
    def validate(self, prop: Proposition) -> ValidationResult:
        # 非 AI 路径（规则引擎）
        rule_result = self.rule_validator.validate(prop)
        
        # Claw-AI 路径（确定性推理）
        claw_result = self.claw_ai.validate(prop)
        
        # 融合
        if claw_result.status == "NEED_LLM":
            # Claw 无法处理，标记为需 LLM
            return ValidationResult(
                status="DEFERRED",
                claw_confidence=None,
                llm_required=True,
                reason=claw_result.reason
            )
        
        return self.fusion_engine.merge(rule_result, claw_result)
```

---

## 双向增强的具体场景

### 场景 1：变量推断（Claw-AI 补全非 AI）

```
输入：公式 "w(n+1) = w(n) + μ * e(n) * x(n)"

非 AI 路径：
  - 模板匹配：LMS 更新模式匹配成功
  - 变量映射：μ → "步长"（模板内置）
  - e → "误差"（模板内置）
  - x → "输入向量"（模板内置）
  - 结果：CERTAIN

Claw-AI 路径（增强）：
  - 上下文分析：此公式出现在"主动噪声控制"章节
  - 学科库检索：μ 在控制领域 = 步长，在声学领域 = 吸收系数
  - 约束推导：公式结构是 LMS → μ 必须是步长（因果律）
  - 结果：CERTAIN + 附加信息（"μ 取值范围 0.001-0.1"）

融合：非 AI 确定 + Claw-AI 增强 = 高置信度 +  richer context
```

### 场景 2：矛盾发现（非 AI 校验 Claw-AI）

```
Claw-AI 推断："S_est 可以在线辨识，延迟 < 40μs"
  - 来源：从上下文推断，作者声称"实时"
  - 推导：若 FPGA 实现，40μs 可能
  - 结果：PROBABLE [0.6, 0.8]

非 AI 路径校验：
  - L3 约束：辨识需要 N 个采样点
  - 量纲分析：N·Ts > 40μs（若 Ts=25μs, N=100 → 2.5ms）
  - 矛盾：2.5ms > 40μs
  - 结果：CONTRADICTION

融合：Claw-AI [0.6, 0.8] + 非 AI CONTRADICTION → [0.0, 0.2]
  → 标记 HALUCINATION
  → Claw-AI 收到反馈，修正推断
```

### 场景 3：Claw-AI 无法处理（标记 NEED_LLM）

```
输入："这个算法的灵感来自于量子纠缠的退相干过程"

非 AI 路径：
  - 无模板匹配
  - 学科库："量子纠缠" → 物理，但公式无关
  - 结果：UNKNOWN

Claw-AI 路径：
  - 跨域类比尝试：振动控制 vs 量子力学
  - 结构签名：无直接匹配
  - 约束对比：物理域差异过大
  - 结果：NEED_LLM（需要开放式类比能力）

融合：标记 DEFERRED，等待 LLM API
```

---

## 与 LLM API 的衔接（未来）

当前架构预留了 LLM 接入点：

```python
class LLMFallback:
    """LLM API 补全层（未来启用）。"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.enabled = api_key is not None
        self.client = None if not self.enabled else OpenAI(api_key=api_key)
    
    def handle_deferred(self, prop: Proposition, claw_reason: str) -> LLMResult:
        """处理 Claw-AI 标记为 NEED_LLM 的命题。"""
        if not self.enabled:
            return LLMResult(status="UNAVAILABLE", reason="LLM not configured")
        
        prompt = self._build_prompt(prop, claw_reason)
        response = self.client.chat.completions.create(...)
        return self._parse_response(response)
```

**过渡策略**：
- Phase 1（现在）：Claw-AI 覆盖 70% 场景，30% 标记 NEED_LLM（暂由人工处理）
- Phase 2（未来）：接入 LLM API，自动处理 NEED_LLM 标记
- Phase 3（成熟）：Claw-AI + LLM 混合，Claw 处理确定性任务，LLM 处理创造性任务

---

## 关键设计决策

### 1. Claw-AI 不是 LLM 的替代品，是**确定性推理层**

- LLM：概率生成，覆盖广，有幻觉
- Claw-AI：规则推导，覆盖窄，无幻觉（但可能遗漏）
- 两者互补：Claw-AI 做边界校验，LLM 做开放推断

### 2. 置信度计算方式不同

| 路径 | 置信度来源 | 可解释性 |
|------|-----------|----------|
| 非 AI | 规则匹配度 + 来源等级 | 100% 可追溯 |
| Claw-AI | 推导链长度 + 约束满足度 | 80% 可追溯（推导步骤可见） |
| LLM | 概率分布（softmax） | 低（黑盒） |

### 3. 失败模式不同

| 路径 | 失败表现 | 检测方式 |
|------|----------|----------|
| 非 AI | 无模板匹配 → UNKNOWN | 显式 |
| Claw-AI | 推导链断裂 → NEED_LLM | 显式（自检） |
| LLM | 幻觉 → 看似合理但错误 | 难检测（需外部校验） |

---

## 实施路径（Claw-AI 版）

| Phase | 任务 | 时间 | 依赖 |
|-------|------|------|------|
| 1 | Proposition Splitter（命题拆分） | 2h | 现有文本清洗 |
| 2 | Claw-AI Validator（变量推断 + 语义解析） | 3h | Phase 1 + L0-L4 |
| 3 | 非 AI ↔ Claw-AI Fusion（融合规则） | 2h | Phase 2 |
| 4 | 自动溯源接口（Retro-Crawler stub） | 2h | Phase 3 |
| 5 | 端到端测试（双向验证闭环） | 2h | Phase 4 |

总计约 11 小时，可分阶段交付。无需 Nemotron，无需 GPU，纯 CPU 运行。

---

## 验证标准

Claw-AI 成功的标准：

1. **覆盖率**：70% 以上的命题可由 Claw-AI 处理（非 NEED_LLM）
2. **准确率**：Claw-AI 推断准确率 > 80%（人工抽检 100 条）
3. **延迟**：单命题处理 < 500ms
4. **双向增强**：非 AI 发现 UNKNOWN → Claw-AI 补全后，系统整体准确率提升 > 15%

如果达标，说明确定性推理层足够支撑副脑核心功能，LLM 只作为增强插件。

---

**是否按此方向实施？** 核心确认点：Claw-AI 作为确定性推理引擎，与 LLM 概率引擎不同质，但可形成"规则边界 + 推理补全"的有效组合。
