# LLM Agent 上下文管理策略调研与 MemoryGraph 方案改进

> **调研范围**：2025-2026 年最新研究（arXiv + 实践博客）
> **评估对象**：MemoryGraph `CONTEXT_COMPRESSION_DESIGN.md` v1.0（2025-06-21）
> **结论**：原方案核心架构正确，但需引入 3 项关键改进以适应 4B 小模型约束。

---

## 一、主流上下文管理策略全景（2025-2026）

### 1. 分层/虚拟内存架构（Hierarchical Virtual Memory）

| 系统 | 年份 | 核心思想 | 对 4B 模型的适用性 |
|------|------|---------|------------------|
| **MemGPT** | 2023 | OS 分页：main context (RAM) → recall storage (disk) → archival (cold) | ★★★ 架构正确，但需简化 |
| **MemTier** | 2026 | 异步守护进程 + RL 自适应检索权重 | ★ 太复杂，不适合 4B |
| **H-MEM** | 2026 | 脑启发层级记忆，learned memory tokens | ★ 需模型修改，不适用 |
| **MemoryBank** | 2023 | 摘要 + 艾宾浩斯遗忘曲线 | ★★ 跨会话有用，但需持久化 |

**结论**：MemGPT 的三层架构（Core/Working/Archive）已被广泛验证，是我们的正确起点。

### 2. 上下文压缩策略（Context Compression）

| 系统 | 年份 | 技术路线 | 开销 | 关键洞察 |
|------|------|---------|------|---------|
| **StreamingLLM** | 2024 | 滑动窗口 + attention sinks，永久丢弃中间 | 零 | 丢弃 = 信息永久丢失，不适合 Agent |
| **LLMLingua** | 2023 | 剪枝低信息 token（up to 20x） | 低 | 对自然语言有效，对工具结果冗余有限 |
| **AgentDiet** | 2025 | GPT-5-mini 在滑动窗口做反射摘要 | 高 | 需要第二个 LLM，4B 无法承受 |
| **ACON** | 2025 | 迭代优化自然语言压缩指南 | 高 | 依赖失败轨迹优化，冷启动差 |
| **Focus** | 2026 | 自主压缩决策：s(c)=αr(c)+βn(c)-γa(c) | 中 | 让 Agent 自己决定何时压缩，**最启发性** |
| **SimpleMem** | 2026 | 语义流水线：过滤→组织层级→自适应检索 | 中 | LoCoMo F1=0.432，state-of-the-art |
| **Context-Folding** | 2026 | 折叠已完成子任务，上下文减少 10x | 低 | **对 ReAct 任务阶段最适用** |

**关键洞察**：
- 纯丢弃（StreamingLLM）不适合 Agent，因为工具结果中的地址、数值等细节不可丢失。
- 4B 模型无法承受双 LLM（AgentDiet 风格）或高频 LLM 调用。
- **Focus 的评分函数**最启发：让压缩决策考虑相关性(relevance)、新颖性(novelty)、年龄(age)。

### 3. 无推理/轻量级压缩（Inference-Free）

| 系统 | 年份 | 核心思想 | 对 4B 的适用性 |
|------|------|---------|--------------|
| **AGORA** | 2026 | 适配器引导的观察-动作保留，避免 LLM 压缩开销 | ★★★★ 理想：零 LLM 开销 |
| **CMV** | 2026 | 结构化无损修剪：去除机械膨胀（原始工具输出、base64、metadata） | ★★★★ 4B 必须：去除工具输出冗余 |
| **Lindenbauer** | 2025 | 固定观察掩码规则，匹配 LLM 摘要质量 | ★★★ 简单但有效 |

**关键洞察**：CMV 的"机械膨胀"概念对 MemoryGraph 极其重要。
我们的工具输出（如 `scan_memory` 返回 1000 个地址）就是典型的机械膨胀——Agent 只需要"42 个匹配地址"这个信息，不需要完整列表。

### 4. 情节分割与任务阶段（Episodic Segmentation）

| 系统 | 年份 | 核心思想 |
|------|------|---------|
| **EM-LLM** | 2025 | 基于"惊喜度"的情节分割，组织为连贯事件 |
| **ReadAgent** | 2024 | 分页 + 要点记忆，用于长文档 |
| **Context-Folding** | 2026 | 折叠已完成子任务 |

**关键洞察**：ReAct 循环天然有任务阶段（扫描→筛选→确认→结论），阶段边界是最佳压缩触发点。

### 5. 检索增强型记忆（RAG for Agent History）

| 系统 | 年份 | 核心思想 | 优先级评估 |
|------|------|---------|----------|
| **A-MEM** | 2025 | 动态索引，无预定义模式 | Phase 2 再考虑 |
| **Mem0** | 2025 | 原子事实提取到向量+图存储 | Phase 2 再考虑 |
| **MemoRAG** | 2025 | 双系统：全局记忆 + 语义检索线索 | Phase 2 再考虑 |
| **StructMem** | 2026 | 层级事件结构 | Phase 2 再考虑 |

**结论**：检索增强对跨会话复用重要，但 Phase 1 应先解决"单会话内不崩溃"。

---

## 二、MemoryGraph 原方案评估

### 原方案架构（v1.0）

```
Layer 3: Core Prompt (~500 tok) — 永不压缩
Layer 2: Compressed Memory (~1500 tok) — 渐进式摘要
Layer 1: Recent Turns (~2000 tok) — 原始滑动窗口
Trigger: 60% 阈值（~2450 tok）时触发 LLM 压缩
```

### 评估矩阵

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构正确性** | ★★★★☆ | MemGPT 三层架构被 2026 年多项研究验证 |
| **阈值设置** | ★★☆☆☆ | 60% 对 4B 模型过高，实际有效推理窗口约 3-5 步 |
| **压缩策略** | ★★☆☆☆ | 每次压缩都调用 LLM，无轻量级预过滤 |
| **阶段感知** | ★☆☆☆☆ | 无任务阶段边界检测，固定步数压缩 |
| **依赖利用** | ★☆☆☆☆ | 依赖图设计但未被压缩器整合 |
| **工具膨胀处理** | ★☆☆☆☆ | scan_memory 返回 1000 地址直接塞入上下文 |
| **持久化** | ★★☆☆☆ | 设计了文件结构但无实现 |

### 核心问题诊断

#### 问题 1：60% 阈值太高
- 4B 模型（Nemotron-3-Nano-4B）实际有效推理窗口约 3-5 步（~1500-2000 tokens）
- 60% 触发时（~2450 tokens），模型已开始出现重复动作、格式混乱
- **修正**：改为固定步数（5 步）或固定 token 数（1500），而非百分比

#### 问题 2：无"机械膨胀"预处理
- `scan_memory` 返回 1000 个地址 → 全部放入上下文 → 即使只保留最近 3 步，也可能 >2000 tokens
- `disassemble` 返回 20 条指令 → 每条指令 JSON 膨胀
- **修正**：工具结果结构化截断（CMV 风格），只保留摘要信息

#### 问题 3：每次压缩都调用 LLM
- 设计图中："利用 80 tok/s 速度，压缩 2K 只需 ~25 秒"
- 实际：每 5 步压缩一次，20 步任务 = 4 次压缩 = 100 秒额外开销
- **修正**：引入"规则预压缩层"（无 LLM 开销）+ "LLM 语义压缩层"（低频触发）

#### 问题 4：无任务阶段边界感知
- 扫描阶段（scan_memory 多次）→ 筛选阶段（read_memory 验证）→ 确认阶段（write/test）→ 结论阶段（conclude）
- 阶段边界是最佳压缩点：前一阶段可以整体摘要
- **修正**：检测工具类型变化作为阶段边界，触发自动压缩

---

## 三、改进方案：Hybrid-Compressor（混合压缩器）

### 核心改进：3-Layer 压缩流水线

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 0: Mechanical De-bloater（机械膨胀去除器）              │
│  ├─ 工具结果截断：scan 返回只保留 count + 前 5 个地址          │
│  ├─ JSON 扁平化：disassemble 结果只保留关键字段                │
│  ├─ 重复观察合并：相同动作多次执行的合并为统计摘要               │
│  └─ 开销：零（纯 Python 字符串处理）                           │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: Stage-Aware Folding（阶段感知折叠）                  │
│  ├─ 检测 ReAct 阶段边界（scan → read → write → conclude）    │
│  ├─ 阶段结束时：将该阶段所有步骤折叠为结构化摘要               │
│  ├─ 触发：动作类型变化（如连续 3 次 scan 后第 1 次 read）      │
│  └─ 开销：零（规则触发）                                      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 2: LLM Semantic Compress（LLM 语义压缩）              │
│  ├─ 触发条件：Layer 0+1 后仍超过阈值（30% 或 1500 tokens）    │
│  ├─ 输入：待压缩的 Recent Turns + 现有 Compressed Memory      │
│  ├─ 输出：结构化摘要（保留关键地址、置信度、因果关系）          │
│  └─ 开销：每次 ~15-25 秒（利用 80 tok/s）                     │
└──────────────────────────────────────────────────────────────┘
```

### 改进后的三层记忆架构

```
Context Window (4B: 4096 tokens, 实际可用 ~3000)
├─ Core Prompt (~500 tok)    [固定]
│   ├─ System Prompt
│   ├─ 任务定义
│   └─ 安全约束
│
├─ Compressed Memory (~1000 tok) [Layer 2 LLM 压缩]
│   ├─ 阶段折叠摘要（Stage summaries）
│   ├─ 高置信度发现（Discoveries）
│   └─ 失败教训（Lessons）
│
└─ Recent Turns (~1500 tok) [Layer 0+1 预处理后]
    ├─ 最近 3-5 步（机械膨胀已去除）
    └─ 当前观察
```

### 触发策略改进

| 原方案 | 改进方案 | 理由 |
|--------|---------|------|
| 60% 阈值（~2450 tok） | 固定 1500 tokens 或 5 步 | 4B 模型有效推理窗口约 1500-2000 tok |
| 仅 Layer 2 LLM 压缩 | Layer 0+1 预处理 + Layer 2 兜底 | 大幅减少 LLM 调用次数 |
| 固定保留最近 2 步 | 阶段边界保留策略 | 阶段切换时保留阶段摘要，而非固定步数 |

### 阶段边界检测（Stage-Aware Folding）

```python
STAGE_TRANSITIONS = {
    "scan_memory": "scan",      # 扫描阶段
    "read_memory": "verify",    # 验证阶段
    "write_memory": "test",     # 测试阶段
    "set_breakpoint": "trace",  # 追踪阶段
    "disassemble": "analyze",   # 分析阶段
    "conclude": "done",         # 完成
}

# 当动作类型从 "scan" 连续 3 次后变为 "read" 时
# 自动将 3 次 scan 的结果折叠为：
# "[SCAN PHASE] 3 scans for value=100 float32 → 42→7→1 addresses"
```

### 机械膨胀去除规则（Mechanical De-bloater）

| 工具 | 原输出 | 去膨胀后 | 节省 |
|------|--------|---------|------|
| `scan_memory` | 1000 个地址列表 | `count=1000, top5=[0x..., ...]` | ~95% |
| `read_memory` | 完整 JSON + raw_bytes | `addr=0x... val=100.0` | ~60% |
| `disassemble` | 20 条完整指令 JSON | `addr=0x...: 5 条关键指令` | ~70% |
| `get_breakpoint_hits` | 10 条完整 hit 记录 | `count=3, last=0x...` | ~80% |

---

## 四、实现规划

### 文件结构

```
core/agents/memory/
├── __init__.py                 # 导出
├── compressor.py               # 新：HybridCompressor（3 层流水线）
├── mechanical_debloat.py       # 新：Layer 0 机械膨胀去除
├── stage_folding.py            # 新：Layer 1 阶段感知折叠
├── prompt_templates.py         # 已设计：LLM 压缩 prompt
├── memory_store.py             # 已设计：持久化存储
├── dependency_graph.py         # 已设计：依赖图（整合到压缩决策）
└── test_compressor.py          # 测试
```

### 关键类：HybridCompressor

```python
class HybridCompressor:
    """3 层混合压缩器：0-去膨胀 → 1-阶段折叠 → 2-LLM 压缩"""
    
    # 配置：4B 模型优化
    CONFIG_4B = {
        "max_context": 3000,           # 实际可用（留 1000 buffer）
        "core_prompt_size": 500,     # Core Prompt 预留
        "recent_max_tokens": 1500,    # Recent 层上限
        "compress_threshold": 1500,   # 触发 LLM 压缩的 token 数
        "max_recent_steps": 5,         # 最多保留 5 步原始
        "stage_fold_enabled": True,   # 启用阶段折叠
        "debloat_enabled": True,      # 启用在膨胀去除
    }
    
    def add_turn(self, step: AgentStep):
        # 1. 工具结果去膨胀
        debloated = MechanicalDebloat.process(step)
        # 2. 添加到 Recent 层
        self.recent_context.append(debloated)
        # 3. 检查阶段边界
        if self.stage_detector.detect_boundary():
            self._fold_stage()
        # 4. 检查是否触发 LLM 压缩
        if self._should_compress():
            self._llm_compress()
```

### 与 ReAct 引擎集成点

```python
class ReactEngine:
    def __init__(self, ...):
        self.memory = HybridCompressor(self.provider, config=HybridCompressor.CONFIG_4B)
        self.memory.set_core_prompt(self.system_prompt)
    
    def _build_observation(self, ...):
        # 不再手动截断历史，由 HybridCompressor 管理
        return self.memory.build_prompt(current_observation)
```

---

## 五、实施优先级

| 优先级 | 模块 | 工作量 | 影响 |
|--------|------|--------|------|
| **P0** | `mechanical_debloat.py` | 2h | 最高：零开销，立即减少 50-90% 上下文膨胀 |
| **P0** | `stage_folding.py` | 3h | 高：零开销，自然压缩阶段 |
| **P1** | `compressor.py` 整合 | 4h | 高：统一 3 层流水线 |
| **P1** | 修改 `react_engine.py` 集成 | 2h | 高：替换现有截断逻辑 |
| **P2** | `memory_store.py` 持久化 | 4h | 中：跨会话复用 |
| **P2** | `dependency_graph.py` 整合 | 3h | 中：保留关键依赖链 |

---

## 六、参考来源

| 论文/系统 | 年份 | 关键贡献 |
|-----------|------|---------|
| MemGPT (Packer et al.) | 2023 | OS 虚拟内存架构 |
| StreamingLLM (Xiao et al.) | 2024 | 滑动窗口 + attention sinks |
| LLMLingua (Jiang et al.) | 2023 | 低信息 token 剪枝 |
| ACON (Kang et al.) | 2025 | 失败轨迹驱动的压缩指南 |
| AgentDiet (Xiao et al.) | 2025 | GPT-5-mini 反射摘要 |
| Focus (Verma) | 2026 | 自主压缩决策评分函数 |
| AGORA | 2026 | 无推理压缩：适配器引导保留 |
| CMV (Santoni) | 2026 | 结构化无损修剪：去除机械膨胀 |
| MemTier | 2026 | RL 自适应检索权重 |
| SimpleMem (Liu et al.) | 2026 | 语义压缩流水线，LoCoMo SOTA |
| Context-Folding | 2026 | 折叠已完成子任务，10x 压缩 |
| EM-LLM (Fountas et al.) | 2025 | 基于惊喜度的情节分割 |
| Memory-R1 (Yan et al.) | 2025 | RL 训练记忆管理 |
| ACC (Bousetouane) | 2026 | 有界内部状态，模式治理 |
| "A Practical Guide to Memory..." | 2026 | 实践者视角，5 大机制家族分类 |
| "MemFail: Stress-Testing..." | 2026 | 记忆系统压力测试基准 |

---

*调研时间：2025-06-22*
*版本：v1.1 改进评估*
