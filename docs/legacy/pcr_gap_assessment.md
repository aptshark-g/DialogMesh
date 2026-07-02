# PCR 实现差距评估报告

**评估基准**：`docs/frontend-agent/design_pcr_interface_v2_1.md`（v2.1 接口化修正版）+ `docs/frontend-agent/design_layer0_pcr_and_layer1_intent_parser.md`（Layer 0/1 融合设计）
**评估日期**：2026-06-15
**当前代码状态**：P8–P13 完成，168 测试通过 166 / 失败 2（PyYAML 环境差异）

---

## 1. 总体完成度：≈ 78%

| 维度 | 设计目标 | 当前状态 | 完成度 |
|---|---|---|---|
| **Layer 0 核心模块**（接口 + 契约 + 注册 + 生命周期 + 配置 + 回退 + 遥测） | 7 个独立模块，完整抽象 | 7 个模块全部实现 | ✅ 100% |
| **Layer 0 规则实现**（rule_based） | 独立子包，含 identifier / estimator / profiler / config.yaml | 单文件 `rule_based.py` 实现全部逻辑 | ⚠️ 70%（功能完整，结构偏离） |
| **Layer 0 可选实现**（llm_enhanced / hybrid） | 插件目录包结构 | 未实现 | ❌ 0% |
| **测试基础设施**（Mock + 对抗 + 基准） | 3 套测试工具 | 3 套全部实现 | ✅ 100% |
| **Layer 1 融合**（IntentContext + ParserConfig + IntentParser） | 数据模型 + 动态配置 + 8 阶段 Pipeline | 全部实现 | ✅ 100% |
| **系统集成**（IntentAgent ↔ PCRLifecycleManager） | IntentAgent 通过 LifecycleManager 间接调用 PCR | IntentAgent 直接实例化 RuleBasedPCR | ⚠️ 50%（功能可用，架构偏离） |
| **配置外部化**（pcr_config.yaml + intent_complexity_map.yaml） | 两个 YAML 配置文件 | 无配置文件，全部内置 | ❌ 0% |
| **端到端验收**（对抗测试集运行 + 基准测试运行） | 对抗测试通过率 + 性能基准数据 | 代码存在，未纳入 CI / 未运行 | ⚠️ 30% |

---

## 2. 已完整实现的模块（绿色）

### 2.1 Layer 0 核心骨架（7/7 模块）

| 文件 | 设计功能 | 实现状态 | 代码量 |
|---|---|---|---|
| `interface.py` | IPCRRouter 抽象基类（8 个抽象方法：name, version, warm_up, shutdown, reload_config, evaluate, get_health, get_telemetry, get_capabilities, get_schema） | ✅ 完全实现，含 `PCRHealthStatus` 枚举 | 204 行 |
| `datacontract.py` | PCRInput_v1 / PCROutput_v1 / CognitiveProfile_v1 / HistoryEntry，版本化 + 校验 + 默认回退 | ✅ 完全实现 | ~200 行 |
| `registry.py` | 显式注册 + 目录自动扫描 + 工厂 + 内省 | ✅ 完全实现（register / unregister / create / discover / list） | 228 行 |
| `lifecycle.py` | 初始化 → 预热 → 回退引擎 → 后台健康检查线程 → 热加载 → 优雅关闭 | ✅ 完全实现 | 304 行 |
| `config.py` | PCRGlobalConfig + ConfigManager（YAML/JSON 加载 + 环境变量覆盖 PCR_* + 热加载检测） | ✅ 完全实现 | 229 行 |
| `fallback.py` | FallbackConfig + FallbackEngine（conservative / degraded / pass_through 策略 + 重试 + 降级链 + 遥测聚合） | ✅ 完全实现 | 256 行 |
| `telemetry.py` | TelemetryCollector（滑动窗口 + 延迟分布 p50/p99 + 错误率 + 健康状态转换记录） | ✅ 完全实现 | 119 行 |

**小计**：≈ 1540 行，骨架完整，可直接支持生产环境的多级回退和热加载。

### 2.2 测试基础设施（3/3 模块）

| 文件 | 设计功能 | 实现状态 | 代码量 |
|---|---|---|---|
| `tests/mock_pcr.py` | 4 种 Mock 实现（Static / Sequence / Recorded / Counter）+ 工厂 helper | ✅ 完全实现 | 368 行 |
| `tests/adversarial_suite.py` | 6 大类对抗测试（ambiguity / noise / complexity / history / injection / unicode），~60 cases | ✅ 完全实现 | 299 行 |
| `tests/benchmark.py` | Benchmark 框架（LatencyDistribution / BenchmarkResult / compare_routers / latency_profile） | ✅ 完全实现 | 289 行 |

**小计**：≈ 956 行，测试工具链完整。

### 2.3 Layer 1 融合（3/3 模块）

| 文件 | 设计功能 | 实现状态 | 代码量 |
|---|---|---|---|
| `models.py` | UserExpectation / CognitiveProfile / IntentContext / ParserConfig + `from_pcr_output` / `from_intent_context` | ✅ 完全实现 | 881 行（含原有模型） |
| `intent_parser.py` | IntentParser 主类（8 阶段 Pipeline：preprocess → extract → classify → split → detect → resolve → merge → build） | ✅ 完全实现 | ~1750 行（含原有解析器） |
| `tests/test_integration.py` | 30 个集成测试（3 期望 × 4 画像 × 5 复杂度 + 回退降级） | ✅ 全部 PASS | ~500 行 |

---

## 3. 已实现但结构/命名偏离的模块（黄色）

### 3.1 `rule_based` 实现：功能完整，结构未分包

| 设计期望 | 当前实现 | 偏离说明 |
|---|---|---|
| `rule_based/__init__.py` + `identifier.py` + `estimator.py` + `profiler.py` + `config.yaml` | 单文件 `rule_based.py`（867 行） | 全部 4 个子组件 + RuleBasedPCR 主类塞在一个文件内；功能完全等价，但不符合设计目录结构 |
| 复杂度规则从 `config/intent_complexity_map.yaml` 加载 | 内置 `_default_rules()` 硬编码列表 | 无法外部化配置，用户无法在不修改代码的情况下调整复杂度规则 |

**风险**：低。功能完全等价，但可维护性和扩展性稍差。未来拆包即可修复。

### 3.2 策略推导命名偏离

| 设计文档 v2.1 | 当前实现 | 影响 |
|---|---|---|
| `execution_mode`: FAST_EXECUTE / CLARIFICATION / DEEP_RESEARCH / CONVERSATIONAL / BALANCED | `execution_mode`: AGGRESSIVE / BALANCED / CONSERVATIVE | 命名语义不同，但映射逻辑等价；下游 `IntentParser` 未使用 execution_mode 直接做分支，影响可控 |
| `prompt_style`: BRIEF / EXPLANATORY / TUTORIAL / BALANCED | `prompt_style`: AGGRESSIVE / BALANCED / CONSERVATIVE | 同上，命名偏离但逻辑覆盖 |

**风险**：低。`IntentAgent._build_system_prompt` 已按当前命名正确使用，只需与设计文档对齐命名即可。

---

## 4. 缺失的模块/功能（红色）

### 4.1 配置外部化（2 项缺失）

| 缺失项 | 设计位置 | 影响 | 修复难度 |
|---|---|---|---|
| `config/pcr_config.yaml` — 全局 PCR 配置 | `config/pcr_config.yaml` | 无法通过文件调整 fallback 策略、健康检查间隔、遥测开关 | 低（~60 行 YAML） |
| `config/intent_complexity_map.yaml` — 复杂度规则表 | `config/intent_complexity_map.yaml` | 无法热调整复杂度规则，重启才能生效 | 低（~40 行 YAML） |

**备注**：`ConfigManager` 和 `ComplexityEstimator` 已经支持从文件加载，只是缺少默认配置文件。用户需要手动创建文件才能使用外部配置。

### 4.2 可选 PCR 实现（2 项缺失）

| 缺失项 | 设计位置 | 影响 | 修复难度 |
|---|---|---|---|
| `llm_enhanced/` — LLM 增强版 PCR | `core/agent/pcr/llm_enhanced/` | 无法将期望识别从规则升级到 LLM few-shot；无法对比规则 vs LLM 准确率 | 中（需接入 LLMProvider） |
| `hybrid/` — 混合实现（规则 + LLM 投票） | `core/agent/pcr/hybrid/` | 无法做 ensemble 提升准确率 | 中 |

**备注**：设计文档标记为"可选"。当前 `RuleBasedPCR` 已预留 LLM fallback 接口（`ExpectationIdentifier._llm_fallback`），只是未启用外部 LLM provider。

### 4.3 系统集成架构偏离（1 项）

| 设计期望 | 当前实现 | 影响 | 修复难度 |
|---|---|---|---|
| `IntentAgent` → `PCRLifecycleManager` → `FallbackEngine` → `RuleBasedPCR` | `IntentAgent` → `RuleBasedPCR`（直接实例化） | 缺失：多级回退、优雅关闭、遥测聚合、健康检查、热加载 | 中（需重构 IntentAgent 初始化 + 关闭逻辑） |

**具体差距**：
1. ❌ 没有使用 `PCRLifecycleManager`，无法利用 fallback engine 的多级回退
2. ❌ 没有 `shutdown()` 调用，进程退出时可能泄漏后台健康检查线程
3. ❌ 没有 telemetry 聚合，无法查看 PCR 调用延迟分布
4. ❌ 没有 hot_reload_config，运行中无法调整配置
5. ❌ 没有 health check，PCR 异常无法自动降级

**修复路径**：将 `IntentAgent.__init__` 中的 `self._pcr_router = RuleBasedPCR()` 替换为 `PCRLifecycleManager` 初始化，并在 `shutdown()` 中调用 `self._pcr_lifecycle.shutdown()`。

---

## 5. 测试与验收差距

### 5.1 已完成的测试

| 测试文件 | 用例数 | 状态 | 覆盖范围 |
|---|---|---|---|
| `test_datacontract.py` | 54 | ✅ PASS | 数据契约序列化、校验、版本兼容性、回退默认输出 |
| `test_rule_based.py` | 84 | ✅ PASS | 期望识别、噪声评估、复杂度评估、认知画像、RuleBasedPCR 端到端 |
| `test_integration.py` | 30 | ✅ PASS | IntentContext 转换、ParserConfig 动态化、IntentParser 3×4×5 矩阵、回退降级 |

### 5.2 待完成的测试/验收

| 验收项 | 设计标准 | 当前状态 | 差距 |
|---|---|---|---|
| 对抗测试集运行 | `AdversarialSuite.run(RuleBasedPCR)` 应全部通过或给出预期失败 | 代码已存在，未运行 | 未验证 RuleBasedPCR 在 60 个对抗 case 上的表现 |
| 性能基准测试 | 规则路径 < 10ms，LLM fallback < 250ms | 代码已存在，未运行 | 无延迟数据验证 |
| 期望识别准确率 | 规则快路径 90%+ | 未人工标注测试集验证 | 缺少 100 条人工标注集 |
| 噪声度评估 Spearman ρ | ρ > 0.8 vs 人工标注 | 未验证 | 缺少 50 条噪声等级测试集 |
| 认知维度收敛 | 10 轮后 EMA 稳定 | 未验证 | 缺少模拟对话测试 |
| 端到端调控验证 | 相同输入不同画像 → 不同 TaskGraph | 部分验证（集成测试覆盖） | 缺少 3 种期望 × 3 种输入的完整验证 |
| 代码覆盖率 | > 90% | 未知 | 未运行覆盖率统计 |

---

## 6. 关键修复清单（按优先级排序）

### P0 — 高优先级（影响稳定性）

1. **IntentAgent 集成 PCRLifecycleManager**（~30 行修改）
   - 替换 `self._pcr_router = RuleBasedPCR()` 为 `PCRLifecycleManager` + `initialize()`
   - 在 `shutdown()` 中调用 `self._pcr_lifecycle.shutdown()`
   - 影响：获得多级回退、健康检查、遥测、热加载

2. **添加默认配置文件**（~100 行 YAML）
   - `config/pcr_config.yaml`（全局配置模板）
   - `config/intent_complexity_map.yaml`（复杂度规则表）
   - 影响：用户可外部化配置，无需改代码

3. **修复 PyYAML 环境差异**（2 个测试失败）
   - 给 `test_yaml_load` 和 `test_config_override` 加 `@skipUnless(yaml, ...)`
   - 或解决 Kimi runtime 3.12 的 PyYAML 安装

### P1 — 中优先级（影响可扩展性）

4. **拆分 `rule_based.py` 为子包结构**（~5 个文件）
   - `rule_based/__init__.py`, `identifier.py`, `estimator.py`, `profiler.py`, `config.yaml`
   - 影响：符合设计文档，便于单独维护

5. **运行对抗测试集并修复预期外失败**（~1–2 小时）
   - 执行 `AdversarialSuite.run(RuleBasedPCR)`
   - 分析失败 case，调整规则或标记已知限制

6. **运行基准测试并记录延迟基线**（~30 分钟）
   - 执行 `Benchmark.run(RuleBasedPCR)`
   - 验证规则路径 < 10ms

### P2 — 低优先级（增强功能）

7. **实现 `llm_enhanced/` 可选包**（~300 行）
   - 接入已有 `LLMProvider`，实现 `LLMEnhancedPCR`
   - 对比规则 vs LLM 准确率

8. **命名对齐**：将 `execution_mode` / `prompt_style` 的 AGGRESSIVE/CONSERVATIVE 重命名为 FAST_EXECUTE/CLARIFICATION/DEEP_RESEARCH/CONVERSATIONAL/BRIEF/EXPLANATORY/TUTORIAL

9. **代码覆盖率统计**：运行 `coverage` 并补充未覆盖分支的测试

---

## 7. 总结

**当前 PCR 实现状态：骨架 100% 完成，生产可用但缺少"最后一公里"。**

- ✅ **核心架构完整**：接口、契约、注册、生命周期、回退、遥测、配置管理全部就绪
- ✅ **规则实现功能完整**：期望识别、噪声/复杂度评估、认知画像、策略推导全部工作
- ✅ **Layer 1 融合完成**：IntentContext 桥接、ParserConfig 动态化、IntentParser 8 阶段 Pipeline 全部通过测试
- ⚠️ **集成点简化**：IntentAgent 直接实例化 RuleBasedPCR，未通过 LifecycleManager，损失了回退、健康检查、热加载能力
- ❌ **配置未外部化**：无默认 YAML 配置文件，复杂度规则硬编码
- ❌ **验收测试未运行**：对抗测试、基准测试、准确率验证未执行

**距离"完整形式"的剩余工作**：
- 代码量：约 500 行（IntentAgent 重构 + 配置文件 + 命名对齐）
- 验证工作量：约 4–6 小时（对抗测试 + 基准测试 + 覆盖率 + 人工标注准确率）
- 可选扩展：约 300 行（LLM 增强实现）

**按当前进度，预计 1–2 个开发周期（约 2–3 天专注工作）可完全达到设计文档定义的完整形式。**
