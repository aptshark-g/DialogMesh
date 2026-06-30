# MemoryGraph 架构设计文档 V3

**版本**: 3.0.0-beta
**日期**: 2026-06-22
**状态**: 重构完成，存储层设计待实现

---

## 1. 项目定位

MemoryGraph 是**自动化逆向推理引擎**（Automated Reverse Engineering Engine），核心目标：

> 从"内存数值锚点"出发，自动回溯反汇编代码中的数据流与控制流，构建"内存变量 ↔ 反汇编指令 ↔ 函数调用关系"的绑定图谱，实现几乎无需人工干预的程序内部逻辑逆向推导。

---

## 2. 核心设计哲学：对抗性逆向工程的四条原则

> 逆向工程不是**解析合作数据**，而是**对抗性信息提取**。
> 目标程序的开发者可能部署了加壳、混淆、反调试、控制流平坦化等保护机制。
> 因此，MemoryGraph 的设计哲学不是"先拆树再推图"的结构主义，而是**基于对抗性假设的多源验证与渐进可信构建**。

---

### 2.1 原则一：对抗性假设（Adversarial Assumption）

**假设：你看到的代码是假的。**

- 静态反汇编看到的可能是**花指令**（虚假跳转）或**加壳后的垃圾代码**（UPX/VMProtect 的 loader stub）
- 动态断点命中时，程序可能正在执行**反调试检查**（检测调试器存在后故意走错误路径）
- 扫描到的"金币地址"可能是一个**诱饵变量**（只被读取，从未被实际游戏逻辑写入）

**设计推论**：
- 单一信息源不可信。任何分析结果必须经过**至少两个独立信息源的交叉验证**。
- 静态分析必须经过**Deobfuscator 层**（反混淆/脱壳）才能进入上层。
- 动态追踪必须结合**符号执行**验证未触发路径，排除"反调试陷阱分支"。
- 每个发现必须携带**置信度（Confidence）**和**证据链（Evidence Chain）**。

---

### 2.2 原则二：多源证据融合（Multi-Source Evidence Fusion）

**三个独立信息源，每个都有偏见：**

| 信息源 | 优势 | 偏见 | 可信度 |
|--------|------|------|--------|
| **静态分析（树/CFG）** | 看到全貌（所有分支、所有函数） | 可能被混淆欺骗（死代码、虚假分支） | 中等 |
| **动态追踪（图/DFG）** | 看到真实执行路径 | 只能看到实际触发的路径（未触发分支不可见） | 高（对已触发部分） |
| **符号执行（约束求解）** | 证明路径可达/不可达 | 只能处理基本块级，路径爆炸问题 | 高（对可求解部分） |

**核心洞察：冲突本身就是信号。**

```
静态 CFG 说："函数 sub_401000 有 5 条分支"
动态 DFG 说："我只抓到 3 条"
符号执行说："第 4 条可达，第 5 条不可达"

融合结果：
  3 条 → confirmed（动态验证）
  1 条 → predicted（符号执行证明可达，但未触发）
  1 条 → dead_code（符号执行证明不可达，可能是混淆陷阱）

冲突驱动下一步：
  predicted → 构造输入触发该分支 → 动态验证 → 升级为 confirmed
  dead_code → 标记为陷阱/残留 → 降低分析优先级
```

**设计推论**：
- **EvidenceAligner** 不是"把两个图合并"，而是**识别冲突、量化置信度、推荐验证行动**。
- LLM 的输入不是"原始汇编"，而是"融合后的对齐报告"（包含冲突摘要和推荐行动）。
- 分析流程是**冲突驱动的迭代**：发现矛盾 → 选择验证策略 → 执行 → 更新置信度 → 发现新矛盾。

---

### 2.3 原则三：架构无关抽象（Architecture-Agnostic Abstraction）

**分析的对象是逻辑，不是汇编。**

```
目标层（LLM 看到）：
  "读取 player->health，加 5，如果等于 100 则跳转到上限处理"

中间层（IR）：
  t1 = LOAD(mem[rbx+0x10, 4])
  t2 = ADD(t1, 5)
  p1 = CMP(t2, 100)
  JZ(p1, 0x1234)

物理层（Zydis 输出）：
  x86:    mov eax, [rbx+0x10]    add eax, 5    cmp eax, 100    jz 0x1234
  ARM64:  LDR W0, [X1, #16]     ADD W0, W0, #5  CMP W0, #100    B.EQ 0x1234
  RISC-V: LW a0, 16(a1)          ADDI a0, a0, 5  LI a1, 100      BEQ a0, a1, 0x1234
```

**设计推论**：
- **P-Code 翻译层（Layer 2）是核心隔离层**。Ghidra 的 P-Code 已经是架构无关的 IR。上层（CFG、符号执行、LLM 分析）**完全不需要知道 CPU 架构**。
- P-Code 翻译目标：**足够简单，LLM 可以直接理解**；**足够精确，能表达内存访问、条件分支、循环、函数调用**。
- 新架构支持只需实现：**新架构 → P-Code 翻译器**（Ghidra 本身已支持 ARM64/RISC-V，无需自研）。无需修改上层任何代码。
- LLM 的 System Prompt 中，工具描述和逻辑分析使用 P-Code 语义描述，而非汇编助记符。

---

### 2.4 原则四：渐进可信标注（Progressive Confidence Labeling）

**每个发现不是"真/假"，而是"目前有多可信"。**

```
置信度演进路径：

[Level 0] 临时猜测（Temporary Guess）
  来源：一次 first_scan 命中
  置信度：0.1-0.3
  寿命：本次会话内（findings 表，TTL 7 天）
  行动：需要 next_scan 缩小范围

[Level 1] 实验验证（Experimental Validation）
  来源：next_scan 多次筛选 + 断点多次命中同一地址
  置信度：0.4-0.7
  寿命：跨会话（node_semantics 表，promoted）
  行动：需要 read_memory 验证值变化，write_memory 验证功能

[Level 2] 逻辑证明（Logical Proof）
  来源：符号执行证明路径可达 + 反汇编/IR 分析确认指令语义
  置信度：0.7-0.9
  寿命：长期知识库（key_registry，promoted_to_core）
  行动：需要多输入条件测试（符号执行求解的触发条件）

[Level 3] 跨会话确认（Cross-Session Confirmation）
  来源：不同进程附加/程序版本更新后，同一逻辑地址/偏移仍然有效
  置信度：0.9-1.0
  寿命：永久（nodes/edges 表，核心本体）
  行动：注入 LLM system prompt，作为"已知语义"直接使用
```

**设计推论**：
- **SchemaGovernor** 的晋升/淘汰机制是这一原则的实现。
- `findings` 表（L3）是临时猜测的容器，TTL 自动清理。
- `node_semantics` 表（L2）是实验验证的容器，LLM 可以引用但会标注置信度。
- `key_registry` 是逻辑证明的容器，**被标记为 promoted_to_core=1 的 key 直接注入 LLM prompt**。
- `nodes` 表（L0/L1）是跨会话确认的核心本体，永不删除。
- LLM 的响应必须包含置信度标注（如：`0x1234 = "health" (confidence: 0.85, evidence: [breakpoint_5_hits, symbolic_proven])`）。

---

### 2.5 三源证据对齐：树与图的关系重构

传统"树与图衔接"假设静态和动态是互补的。但对抗性场景下，它们**可能互相矛盾**。需要三源对齐：

```
                    ┌──────────────────────────────────────┐
                    │         EvidenceAligner               │
                    │    (融合静态 + 动态 + 符号执行)       │
                    └─────────────────┬────────────────────┘
                                      │
           ┌──────────────────────────┼──────────────────────────┐
           │                          │                          │
           ▼                          ▼                          ▼
    ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
    │ 静态 CFG     │          │ 动态 DFG     │          │ 符号执行     │
    │ (Top-Down)   │          │ (Bottom-Up)  │          │ (Proof)      │
    │              │          │              │          │              │
    │ 优势：全貌   │          │ 优势：真实   │          │ 优势：可达性 │
    │ 偏见：可能被 │          │ 偏见：碎片   │          │ 偏见：路径爆炸│
    │ 混淆欺骗     │          │ 偏见：遗漏   │          │              │
    └──────────────┘          └──────────────┘          └──────────────┘
           │                          │                          │
           │  冲突信号                │  验证信号                │  证明信号
           ▼                          ▼                          ▼
    "这里有5条分支"           "只触发了3条"              "第4条可达，第5条不可达"
           │                          │                          │
           └──────────────┬───────────┴──────────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │   融合后状态          │
              │   ┌─────────────┐   │
              │   │ confirmed   │ 3 │  (动态验证 + 符号执行一致)
              │   │ predicted   │ 1 │  (符号执行可达，动态未触发)
              │   │ dead_code   │ 1 │  (符号执行不可达，静态声称可达)
              │   └─────────────┘   │
              │                     │
              │ 冲突驱动行动：       │
              │  predicted → 构造输入 → 动态验证 → 升级为 confirmed
              │  dead_code → 标记陷阱 → 降低优先级 → 可能上报给用户
              └─────────────────────┘
```

**对齐不是合并，是冲突检测与置信度仲裁。**

静态说"可达"、动态说"不可达"、符号执行说"不可达" → **dead_code**（一致：静态预测错误，可能是混淆）
静态说"可达"、动态说"不可达"、符号执行说"可达" → **hard_to_trigger**（冲突：需要特定输入，动态只是没触发）
静态说"不可达"、动态说"可达" → **runtime_generated**（冲突：运行时生成代码，静态看不到）

**LLM 看到的结果**：
```
函数 sub_401000 分析结果：
- 3 条路径已确认（动态命中 15 次）
- 1 条路径预测可达（符号执行证明，建议构造输入 eax < 0 触发）
- 1 条路径标记为死代码（可能是 VMProtect 的陷阱分支）

推荐下一步：验证 predicted 路径（需要修改金币为负数）
```

---

### 2.6 旧设计哲学的遗留定位

以下概念作为**实现策略**保留，但不再是"核心哲学"：

- **自顶向下（Top-Down）**：静态分析的策略，用于**缩小搜索空间**（先分析模块/段，再定位函数）。但静态结果必须经过反混淆验证。
- **自底向上（Bottom-Up）**：动态追踪的策略，用于**获取真实证据**（断点命中、扫描验证）。但动态结果只能覆盖已触发路径，需要符号执行补充未触发路径。
- **树与图**：两种数据结构的表现形式。树用于**静态结构导航**（模块→函数→基本块），图用于**动态关系表达**（指令→变量→结构体）。但在对抗性场景下，它们的**冲突比对**比**衔接合并**更重要。

**核心哲学转变**：
```
旧：先拆树再推图，静态动态互补 → 简单结构主义
新：三源独立验证，冲突驱动迭代，渐进可信标注 → 对抗性信息论
```

---

## 3. 系统架构总览

### 3.1 致命缺口声明（2026-06-22 补充）

当前架构在以下四个维度存在**致命缺口**，直接限制引擎对真实世界软件的适应能力：

| 缺口 | 严重程度 | 影响 | 说明 |
|------|---------|------|------|
| **Ghidra 静态→动态衔接层缺失** | 🔴 致命 | 跨架构分析受限，LLM 只能理解汇编而非伪 C 代码 | Ghidra 已做静态分析（P-Code/反编译），但无实时运行时衔接：内存镜像未自动导出、反编译结果未注入动态断点命中、静态 CFG 与动态 DFG 未实时对齐。动态追踪命中某地址时，系统无法立即查询 "这是 Ghidra 识别的哪个函数？反编译代码是什么？" |
| **Angr / Z3 符号执行 + 静态 CFG 未集成** | 🔴 致命 | 条件分支无法自动破解，函数全貌不可见 | 文档中规划了自研 `StaticCFGBuilder` 和 `SymbolicExecutor`，但 Angr（UC Santa Barbara 的 Shellphish 团队开发）已完整实现符号执行 + 静态 CFG + 约束求解（内部集成 Z3）。自研等于重复造轮子。当前未安装 Angr（`pip install angr` 即可），`z3` 仅文档提及。 |
| **全局静态 CFG 缺失** | 🟠 严重 | 看不到函数全貌拓扑 | 自顶向下只到基本块，动态追踪是碎片路径，无法构建完整控制流图 |
| **抗混淆 / 反调试缺失** | 🟠 严重 | 对保护软件完全无效 | 无脱壳（UPX/VMProtect）、无反花指令、无控制流平坦化检测 |
| **证据对齐算法缺失** | 🟠 严重 | 树与图无法融合 | 静态 CFG 与动态 DFG 存在分歧（死代码 vs 未触发分支），无融合算法 |

**没有 Ghidra 静态分析衔接，动态追踪只能看到无意义的地址和汇编，LLM 无法理解程序逻辑；**没有符号执行，条件分支是黑箱；没有 CFG，看不到程序全貌；没有反混淆，遇到保护软件直接崩溃。

---

### 3.2 修正后的分层架构

```
┌────────────────────────────────────────────────────────────────────┐
│  Layer 7: 交互与可视化层                                           │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │ Flask Web GUI    │ │ ECharts 图谱渲染 │ │ 报告导出 (Markdown)│ │
│  │ (8080 端口)      │ │ (DFG/MRG/CFG/IR) │ │ (HTML/PDF/伪C)     │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│  Layer 6: AI Agent 层                                              │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │ IntentAgent      │ │ WorkflowEngine   │ │ AgentEngine        │ │
│  │ (交互式 Act 模式) │ │ (自动化工作流)   │ │ (多 Agent 编排)    │ │
│  │ - 工具结果外部化  │ │ - 状态机驱动     │ │ - 任务调度         │ │
│  │ - 上下文压缩      │ │ - 一键分析       │ │ - 结果聚合         │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│  Layer 5: 压缩与记忆层 (纯内存)                                    │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │ HybridCompressor │ │ StageFolder      │ │ DeBloater          │ │
│  │ (3层混合压缩)    │ │ (阶段感知折叠)   │ │ (机械膨胀去除)     │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│  Layer 4: 图构建与证据对齐层 (纯内存 → SQLite)                     │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │ DFGGraph         │ │ MemoryRelationshipGraph                 │ │
│  │ (数据流图)       │ │ (指令级结构图)   │                        │
│  │ - 运行时依赖     │ │ - 结构体推断     │                        │
│  ├──────────────────┴──────────────────┴──────────────────────┤ │
│  │ EvidenceAligner (证据对齐) ── 静态 CFG + 动态 DFG 融合      │ │
│  │ - 静态/动态路径一致性检验                                   │ │
│  │ - 死代码标记 / 未触发分支推测                               │ │
│  │ - 置信度加权融合                                            │ │
│  └──────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│  Layer 3: 分析层 (开源工具 + 自研桥接)                               │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │ ProcessAnalyzer  │ │ Scanner          │ │ Debugger           │ │
│  │ (进程/模块/段)   │ │ (内存扫描)         │ │ (断点/追踪)        │ │
│  ├──────────────────┴──────────────────┴──────────────────────┤ │
│  │ AngrBridge (符号执行 + 静态 CFG + 约束求解)              │ │
│  │ - `pip install angr` ── 完整符号执行引擎 (Shellphish)    │ │
│  │ - CFGFast: 函数级 CFG 构建 (含间接跳转解析)               │ │
│  │ - SimulationManager: 路径探索 + 约束收集                  │ │
│  │ - Claripy (Z3 封装): 求解触发条件 → 具体输入值            │ │
│  │ - 自研: AngrBridge 桥接层 (动态追踪 → 符号执行种子引导)   │ │
│  ├──────────────────────────────────────────────────────────────┤ │
│  │ 开源工具矩阵 (按需集成)                                      │ │
│  │ - Z3 (`z3-solver`): 基本块级快速约束求解 (独立使用)         │ │
│  │ - Unicorn (`unicorn`): CPU 模拟验证 (求解结果安全测试)      │ │
│  │ - Frida (`frida-tools`): 跨平台动态插桩 (替代 Windows API)│ │
│  │ - Capstone (`capstone`): 多架构反汇编 (ARM64/MIPS 回退)    │ │
│  └──────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│  Layer 2: Ghidra 集成层 (静态→动态衔接) ── 🔴 待完善           │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │ GhidraBridge     │ │ PCodeTranslator  │ │ DecompilerBridge  │ │
│  │ (静态分析导入)    │ │ (P-Code → 简化语义)│ │ (反编译 → LLM 提示)│ │
│  │ - 内存镜像导出    │ │ - 寄存器 → SSA    │ │ - 函数伪 C 代码   │ │
│  │ - 函数/结构体导入 │ │ - 内存访问抽象    │ │ - 实时值注入      │ │
│  │ - CFG 导入       │ │ - 控制流谓词       │ │ - 动态增强注释   │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│  Layer 1: 底层引擎 (硬件 + 混淆对抗)                               │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │ mg_engine.dll    │ │ Zydis (v4.1.1)   │ │ Deobfuscator     │ │
│  │ (C++ 加速)       │ │ (反汇编引擎)       │ │ (反混淆/脱壳)      │ │
│  │ - 内存扫描加速    │ │ - 指令解码       │ │ - 壳检测 (UPX/VM) │ │
│  │ - 指针链扫描      │ │ - 操作数解析       │ │ - 花指令去除      │ │
│  │ - 时序追踪        │ │ - 控制流检测       │ │ - 平坦化还原      │ │
│  │                  │ │                  │ │ - 反调试绕过      │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│  Layer 0: 系统接口                                                 │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │ Windows API      │ │ psapi            │ │ ctypes               │ │
│  │ (OpenProcess等)  │ │ (EnumProcessModulesEx) │ │ (Python 绑定)      │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

**关键设计原则**：
- **Ghidra P-Code 层 (Layer 2)** 是"架构无关的胶水层"，位于反汇编之上、分析层之下。Ghidra 的 P-Code 已经把 x86/ARM/RISC-V 的汇编统一翻译为架构无关的 IR，我们只需将其翻译为 LLM 可理解的简化语义描述。上层分析**完全不需要知道 CPU 架构**。
- **符号执行 (Layer 3)** 与静态 CFG 是**孪生兄弟**：CFG 提供路径拓扑，符号执行提供路径条件。两者联动：动态断点未覆盖的分支 → 符号执行探索 → 生成输入触发该分支 → 断点验证。
- **反混淆 (Layer 1)** 是**前置过滤层**：所有静态分析（CFG、P-Code/反编译）的输入必须先经过反混淆。如果检测到 VMProtect，必须先脱壳或切换为纯动态分析策略。
- **证据对齐 (Layer 4)** 是**核心算法层**：静态 CFG 说"这里有 5 条分支"，动态 DFG 说"我只抓到 3 条" → 对齐算法标记 2 条未触发分支为"待验证"，触发符号执行或引导 Agent 提问用户。

### 3.2 修正后的模块依赖图（含新层）

```
                      ┌──────────────┐
                      │  gui/server  │
                      │  (Flask API) │
                      └──────┬───────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │IntentAgent│ │WorkflowEngine│ │AgentEngine│
        │(Act Loop) │ │(State Mach) │ │(Multi-Agt)│
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             └────────────┼────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │AgentContext  │
                   │(findings+   │
                   │_tool_cache) │
                   └──────┬───────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
              ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │DFGGraph  │ │MRG       │ │Evidence  │
        │(内存)    │ │(内存)    │ │Aligner   │
        └──────────┘ └──────────┘ └──────────┘
              │           │           │
              └───────────┼───────────┘
                          │
                          ▼
              ┌───────────┼───────────┐
              │           │           │
              ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │StaticCFG │ │Symbolic  │ │Process   │
        │Builder   │ │Executor  │ │Analyzer  │
        └──────────┘ └──────────┘ └──────────┘
              │           │           │
              └───────────┼───────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  GhidraBridge│
                   │PCodeTranslator│
                   │DecompilerBridge│
                   └──────┬───────┘
                          │
                          ▼
              ┌───────────┼───────────┐
              │           │           │
              ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Deobfusca-│ │ mg_engine│ │  Zydis   │
        │  tor     │ │   .dll   │ │ (v4.1.1) │
        └──────────┘ └──────────┘ └──────────┘
```

---

## 4. 致命缺口层详细设计

### 4.1 Layer 2: IR 与反编译层（架构无关的胶水层）

**为什么必须有？**
- 项目已有 Ghidra 做静态分析（`ghidra_scripts/ExportStructAccess.java`、`tracer_v2.py` 的 GhidraBridge 交叉验证），但**Ghidra 是静态分析工具，无法实时衔接运行中的进程**
- 当动态断点命中 0x401234 时，系统需要立即知道"这是 Ghidra 识别的哪个函数？反编译代码是什么？参数类型是什么？"
- 当动态追踪发现 `[rcx+0x48]` 访问时，需要对比 Ghidra 的静态结构推断，修正结构体大小/字段偏移
- 没有衔接层，Ghidra 的静态分析成果（P-Code、反编译、函数签名、结构体）无法在动态追踪中实时利用

**为什么不用 Ghidra 直接做动态分析？**
- Ghidra 分析磁盘上的 PE 文件，不是内存中的运行进程
- 加壳程序（UPX/VMProtect）在磁盘上是混淆的，内存中才是解密后的真实代码
- 动态数值变化（扫描、断点命中）Ghidra 无法观察
- Ghidra 启动开销 10-30 秒，无法毫秒级响应断点命中

**Ghidra 集成层设计目标**：
- 附加进程时，导出主模块内存镜像，触发 Ghidra Headless 分析
- 导入 Ghidra 分析结果（函数列表、反编译代码、P-Code、结构体、CFG）到 SQLite 知识库
- 动态断点命中时，实时查询 Ghidra 知识库：地址 → 函数 → 反编译代码 → 注入 LLM prompt
- 动态追踪发现与 Ghidra 静态推断冲突时（如访问了 [base+0x48] 但 Ghidra 结构体只到 0x40），自动修正结构体

**组件设计**：

```python
class GhidraBridge:
    """Ghidra Headless 集成桥。"""
    
    def __init__(self, ghidra_path: str, project_dir: str):
        self.ghidra_headless = ghidra_path
        self.project_dir = project_dir
        self._analysis_cache: Dict[str, GhidraAnalysisResult] = {}  # 模块哈希 → 分析结果
        
    def analyze_module(self, module_dump_path: str, module_name: str) -> GhidraAnalysisResult:
        """
        1. 调用 Ghidra Headless 分析内存镜像文件
           analyzeHeadless <project_dir> <project_name> 
             -import <module_dump_path> 
             -analysisTimeoutPerFile 60
             -postScript ExportStructAccess.java <output_json_path>
        2. 等待分析完成，读取 JSON 输出
        3. 解析结果：函数列表、结构体访问模式、反编译代码片段
        4. 存入 _analysis_cache（以模块哈希为键，避免重复分析相同版本）
        """
        
    def get_function_at(self, address: int) -> Optional[GhidraFunctionInfo]:
        """查询地址所属的函数信息。"""
        # 返回: {name: "sub_401000", decompiled: "void func(int* a1)", 
        #        params: [{name: "a1", type: "int*", register: "rcx"}]}
        
    def get_struct_access_at(self, address: int) -> List[StructAccess]:
        """查询该地址处的结构体访问模式（从 Ghidra 静态分析导出）。"""
        # 返回: [{base_reg: "rcx", offset: 0x10, size: 4, inferred_name: "health"}]
        
    def get_pcode_at(self, address: int) -> List[PCodeOp]:
        """获取该地址的 P-Code 操作序列。"""
        # Ghidra P-Code 是官方 IR，比自研 IR 更完整、更精确
        # 返回简化后的 P-Code 列表供 LLM 理解

class PCodeTranslator:
    """将 Ghidra P-Code 翻译为 LLM 可理解的简化语义描述。"""
    
    # 不需要重新定义 IR，Ghidra 的 P-Code 已经是 IR
    # 只需要：P-Code → 自然语言摘要
    
    def translate_to_semantic(self, pcode_ops: List[PCodeOp], 
                              dynamic_state: Optional[Dict] = None) -> str:
        """
        将 P-Code 操作序列翻译为语义描述。
        
        输入（P-Code）:
          LOAD ram($U0:8) = *[ram]int32_t (RBX + 0x10:8)
          INT_ADD EAX = $U0 + 5:4
          INT_EQUAL $U1 = EAX == 100:4
          CBRANCH [0x1234:8], $U1
          STORE *[ram] (RBX + 0x10:8) = EAX
        
        输出（语义描述，供 LLM 理解）:
          "从 [RBX+0x10] 读取 int32_t，加 5，比较是否等于 100，
           如果等于则跳转到 0x1234，最后写回 [RBX+0x10]"
        
        如果提供了 dynamic_state（断点命中时的寄存器值）:
          "RBX = 0x7FF6A00B1234 (Player* player_ptr)
           读取 player->health = 95
           加 5 → 100
           等于 100 → 触发条件，跳转 0x1234 (level_up_handler)
           写回 player->health = 100"
        """

class DecompilerBridge:
    """将 Ghidra 的反编译结果与动态数据结合，生成增强型 LLM 提示。"""
    
    def build_function_context(self, eip: int, 
                                dynamic_registers: Dict[str, int]) -> str:
        """
        1. 查询 Ghidra：EIP 属于哪个函数？获取反编译代码
        2. 将动态寄存器值注入反编译代码的变量注释中
        3. 输出增强型伪 C 代码 + 实时值注释
        
        示例输出:
        ```c
        // 函数: Player::UpdateHealth (Ghidra 识别)
        // 反编译代码:
        void __fastcall Player_UpdateHealth(Player *this, int delta)
        {
            // 动态值: this = 0x7FF6A00B1234 (Player*)
            // 动态值: delta = 5
            int current = this->health;  // 当前值: 95 (从 [RBX+0x10] 读取)
            current += delta;            // 95 + 5 = 100
            if (current == 100) {        // 条件成立！
                // 跳转到 0x1234
                LevelUp(this);           // 调用等级提升函数
            }
            this->health = current;      // 写回 100
        }
        ```
        """
        
    def correct_struct_from_dynamic(self, static_struct: StructDefinition,
                                    dynamic_accesses: List[MemoryAccess]) -> StructDefinition:
        """
        当动态追踪发现访问了静态结构体未覆盖的偏移时，修正结构体。
        
        例如:
        Ghidra 静态推断: Player 结构大小 0x40，字段到 offset 0x3C
        动态追踪: 断点命中时访问了 [RBX+0x48]
        
        修正:
        - 扩展结构体大小到 0x50
        - 添加字段 "field_0x48" (int32_t，需后续语义标注)
        - 更新 SQLite 中的结构体定义
        - 生成新的 Ghidra 导入脚本 (v2_ghidra_import_*.java)
        """
```

**Ghidra 分析结果导入知识库**：

```python
class GhidraImporter:
    """将 Ghidra 分析结果导入 SQLite 知识库。"""
    
    def import_analysis(self, result: GhidraAnalysisResult, project_id: str):
        """导入 Ghidra 的静态分析结果到 nodes/edges 表。"""
        
        # 1. 导入函数节点
        for func in result.functions:
            self.db.insert_node(
                project=project_id,
                id=f"{project_id}:function:{func.address}",
                type="function",
                name=func.name,
                address=func.address,
                size=func.size,
                properties=json.dumps({
                    "decompiled": func.decompiled_code,
                    "parameters": func.parameters,
                    "return_type": func.return_type,
                    "ghidra_confidence": func.confidence,
                }),
                tree_path=f"/process/{result.module_name}/.text/{func.name}"
            )
            
        # 2. 导入结构体定义
        for struct in result.structures:
            self.db.insert_node(
                project=project_id,
                id=f"{project_id}:struct:{struct.name}",
                type="struct",
                name=struct.name,
                size=struct.size,
                properties=json.dumps({
                    "fields": struct.fields,
                    "ghidra_source": "auto_analysis",
                })
            )
            
        # 3. 导入结构体访问边（函数 → 结构体字段）
        for access in result.struct_accesses:
            self.db.insert_edge(
                project=project_id,
                source=f"{project_id}:function:{access.function_addr}",
                target=f"{project_id}:struct_field:{access.struct_name}:{access.offset}",
                type="struct_field_access",
                properties=json.dumps({
                    "offset": access.offset,
                    "size": access.size,
                    "instruction_addr": access.instruction_addr,
                })
            )
```

**与动态追踪的衔接示例**：

```
用户附加进程 game.exe (PID 1234)
  ↓
MemoryGraph: 导出主模块内存镜像 → game.exe.dump
  ↓
GhidraBridge: 调用 Ghidra Headless 分析 game.exe.dump
  ↓
Ghidra: 自动分析完成，导出结果:
  - 识别 1,247 个函数
  - 反编译 342 个函数
  - 推断 23 个结构体
  - 结构体访问模式: 8,491 条
  ↓
GhidraImporter: 导入 SQLite 知识库
  ↓
用户: "找到金币数量"
  ↓
IntentAgent: first_scan → 候选地址 0x7FF6A00B1234
  ↓
用户: "在第一个地址设置断点，花掉金币"
  ↓
Debugger: 断点命中！EIP = 0x401000
  ↓
GhidraBridge.get_function_at(0x401000):
  → 函数: "Player::SpendMoney" (Ghidra 自动命名)
  → 反编译代码: "void __fastcall Player_SpendMoney(Player* this, int amount)"
  → P-Code: 显示 [RBX+0x10] 是 this->gold 字段
  ↓
DecompilerBridge.build_function_context(0x401000, registers):
  → 生成增强伪 C 代码，注入实时值:
     "this = 0x7FF6A00B1234 (Player*), amount = 10
      this->gold = 95;  // 读取
      this->gold -= 10; // 95 - 10 = 85
      this->gold = 85;  // 写回"
  ↓
IntentAgent: LLM 分析 → "这是金币消耗函数，RBX+0x10 是金币字段"
  ↓
PCodeTranslator: 将 P-Code 翻译为语义 → 确认结构体偏移
  ↓
GhidraImporter.correct_struct_from_dynamic():
  → 如果动态访问了 [RBX+0x48] 但 Ghidra 结构体只到 0x40
  → 扩展结构体，添加新字段
  → 生成新的 Ghidra 导入脚本
```

**实现优先级**：
- **Phase 1**: Ghidra Headless 调用封装（analyzeHeadless 命令行调用）
- **Phase 2**: 分析结果 JSON 解析 + SQLite 导入
- **Phase 3**: 动态断点命中时实时查询 Ghidra 知识库
- **Phase 4**: 结构体动态修正（对比静态推断与动态访问）
- **Phase 5**: P-Code 简化翻译（供 LLM 理解）
- **Phase 6**: 反编译代码 + 动态值注入（增强型 LLM 提示）

---

### 4.2 Layer 3: 静态 CFG 与符号执行

### 4.2 Layer 3: Angr 集成层（符号执行 + 静态 CFG + 约束求解）

> **核心原则：不重复造轮子。** Angr（UC Santa Barbara Shellphish 团队）已完整实现符号执行、静态 CFG、约束求解（内部封装 Z3/Claripy）。文档中规划的自研 `StaticCFGBuilder` 和 `SymbolicExecutor` 是重复造轮子。
>
> **我们的自研价值**：不是重新实现符号执行，而是构建 **AngrBridge** —— 将动态追踪数据作为 Angr 的初始状态（种子引导），缩小搜索空间；将 Angr 的符号执行结果与动态追踪对比，识别未触发分支。

**为什么必须用 Angr 而不是自研？**

| 维度 | 自研 SymbolicExecutor | Angr（开源） |
|------|----------------------|-------------|
| 开发成本 | 6-12 个月（全职团队） | `pip install angr`（已存在） |
| 功能完整度 | 基本块级，x86  only | 函数级/程序级，x86/ARM/MIPS/PowerPC/... |
| 间接跳转解析 | 需自行实现 heuristics | `CFGFast` 自动解析跳转表、函数指针 |
| 路径爆炸处理 | 无策略 | 内置 DFS/BFS/循环限制/合并策略 |
| 约束求解 | 需手动集成 Z3 | 内置 Claripy（Z3 封装） |
| 系统调用模拟 | 需自行实现 | 内置 SimProcedures（200+ 系统调用） |
| 社区验证 | 0 个真实案例 | 10 年+ CTF/学术/工业验证 |

**自研的唯一理由不存在**：我们不是做学术研究（发论文），而是做工程产品。Angr 的 LGPL 许可证允许我们集成和修改。

**Angr 集成设计**：

```python
import angr
import claripy

class AngrBridge:
    """桥接 Angr 符号执行与 MemoryGraph 动态追踪。"""
    
    def __init__(self, module_dump_path: str):
        """
        加载内存镜像（从附加进程导出的 dump）到 Angr。
        
        注意：需要内存镜像包含完整的加载基址和重定位信息，
        或手动指定 load_options={'main_opts': {'base_addr': ...}}。
        """
        self.project = angr.Project(
            module_dump_path,
            load_options={'auto_load_libs': False}
        )
        self.cfg = None
        self._cfg_cache: Dict[str, any] = {}  # 模块哈希 → CFG
        
    def build_cfg(self, force_rebuild=False) -> angr.analyses.CFGFast:
        """构建静态 CFG（含间接跳转解析）。
        
        Angr 的 CFGFast 能力：
        - 基本块识别、边构建（跳转/调用/返回）
        - 间接跳转解析（跳转表模式匹配、函数指针分析）
        - 可达性分析（标记不可达块为 dead code）
        - 循环检测（自然循环识别）
        - 函数边界识别（含非标准函数序言）
        
        结果存入 SQLite 知识库（nodes/edges 表），与 Ghidra 结果对比。
        """
        if self.cfg is not None and not force_rebuild:
            return self.cfg
            
        self.cfg = self.project.analyses.CFGFast(
            normalize=True,
            force_complete_scan=True,
            resolve_indirect_jumps=True,  # 自动解析跳转表
        )
        return self.cfg
        
    def analyze_function(self, func_addr: int,
                         dynamic_trace: Optional[DFGGraph] = None) -> AngrFunctionResult:
        """分析指定函数，结合动态追踪数据。"""
        
        # 1. 获取函数级 CFG（从已构建的全局 CFG）
        cfg = self.build_cfg()
        func = cfg.kb.functions[func_addr]
        
        # 2. 提取基本块和分支信息
        blocks = []
        for block_addr in func.block_addrs:
            block = self.project.factory.block(block_addr)
            blocks.append({
                'addr': block_addr,
                'size': block.size,
                'insns': block.capstone.insns,  # Capstone 反汇编
                'has_branch': block.vex.jumpkind != 'Ijk_Boring',
            })
        
        # 3. 符号执行：探索未触发的分支
        uncovered_paths = []
        if dynamic_trace:
            # 动态已覆盖的基本块
            dynamic_blocks = set(dynamic_trace.executed_blocks)
            
            # 静态 CFG 中的所有块
            static_blocks = set(func.block_addrs)
            
            # 未覆盖的块 → 用符号执行探索如何触发
            uncovered = static_blocks - dynamic_blocks
            for block_addr in uncovered:
                # 符号执行：从函数入口到目标块
                result = self._symbolic_execute_to_block(func_addr, block_addr)
                if result and result.satisfiable:
                    uncovered_paths.append({
                        'target': block_addr,
                        'input_constraints': result.constraints,
                        'concrete_inputs': result.concrete_inputs,
                    })
        
        return AngrFunctionResult(
            cfg=func.transition_graph,
            blocks=blocks,
            uncovered_paths=uncovered_paths,
        )
        
    def _symbolic_execute_to_block(self, start_addr: int, target_addr: int,
                                   timeout: int = 30) -> Optional[SymbolicResult]:
        """符号执行：从 start_addr 到 target_addr，求解触发条件。
        
        使用 Angr 的 SimulationManager 进行路径探索。
        策略：以动态追踪数据为初始状态（种子引导），缩小搜索空间。
        """
        # 创建初始状态（空白符号状态或注入动态寄存器值）
        state = self.project.factory.call_state(start_addr)
        
        # 可选：注入动态追踪的寄存器值作为约束（种子引导）
        # state.regs.rax = claripy.BVV(known_rax_value, 64)
        
        simgr = self.project.factory.simulation_manager(state)
        
        # 探索直到找到 target_addr 或超时
        simgr.explore(find=lambda s: s.addr == target_addr, timeout=timeout)
        
        if simgr.found:
            found_state = simgr.found[0]
            # 求解触发该路径的输入值
            solver = found_state.solver
            concrete = {}
            for sym in solver.variables:
                val = solver.eval(sym)
                concrete[str(sym)] = val
            
            return SymbolicResult(
                satisfiable=True,
                constraints=found_state.solver.constraints,
                concrete_inputs=concrete,
            )
        
        return SymbolicResult(satisfiable=False)
        
    def solve_input_for_path(self, func_addr: int, path: List[int]) -> Optional[Dict[str, int]]:
        """求解触发特定路径（按基本块地址列表）的输入值。"""
        state = self.project.factory.call_state(func_addr)
        simgr = self.project.factory.simulation_manager(state)
        
        # 按路径顺序探索
        for target in path:
            simgr.explore(find=lambda s, t=target: s.addr == t, timeout=10)
            if not simgr.found:
                return None
            simgr = self.project.factory.simulation_manager(simgr.found[0])
        
        # 求解最终状态的输入
        solver = simgr.active[0].solver
        concrete = {}
        for sym in solver.variables:
            val = solver.eval(sym)
            concrete[str(sym)] = val
        return concrete
        
    def import_to_knowledge_base(self, project_id: str, db: ReverseEngineeringGraph):
        """将 Angr 分析结果导入 SQLite 知识库。"""
        cfg = self.build_cfg()
        
        # 导入函数节点
        for func_addr, func in cfg.kb.functions.items():
            db.insert_node(
                project=project_id,
                id=f"{project_id}:function:{func_addr}",
                type="function",
                name=func.name,
                address=func_addr,
                size=func.size,
                properties=json.dumps({
                    "blocks": list(func.block_addrs),
                    "is_syscall": func.is_syscall,
                    "is_plt": func.is_plt,
                    "angr_source": "CFGFast",
                }),
                tree_path=f"/process/main/.text/{func.name}"
            )
        
        # 导入控制流边
        for edge in cfg.graph.edges:
            src, dst = edge
            db.insert_edge(
                project=project_id,
                source=f"{project_id}:block:{src}",
                target=f"{project_id}:block:{dst}",
                type="control_flow",
                properties=json.dumps({"angr_edge_type": cfg.graph.edges[edge].get("jumpkind", "unknown")})
            )
```

**Z3 独立使用（基本块级快速求解）**：

```python
from z3 import Solver, BitVec, sat

class Z3QuickSolver:
    """独立于 Angr 的 Z3 快速约束求解器。
    
    用途：当 Angr 的路径探索开销过大时（函数太复杂），
    对单个基本块或简单路径条件进行快速求解。
    """
    
    def solve_branch_condition(self, cmp_insn: Dict, 
                              dynamic_registers: Dict[str, int]) -> Optional[str]:
        """求解分支条件的触发方向。
        
        示例：
        cmp eax, 100  →  求解 eax 取什么值时走 true/false 分支
        """
        solver = Solver()
        
        # 创建符号变量
        eax = BitVec('eax', 32)
        
        # 从动态寄存器值获取已知约束（如果已知）
        if 'eax' in dynamic_registers:
            solver.add(eax == dynamic_registers['eax'])
        
        # 分支条件：eax == 100
        condition = eax == 100
        
        # 求解 true 分支
        solver.push()
        solver.add(condition)
        if solver.check() == sat:
            model = solver.model()
            true_result = model[eax].as_long()
        solver.pop()
        
        # 求解 false 分支
        solver.push()
        solver.add(condition == False)
        if solver.check() == sat:
            model = solver.model()
            false_result = model[eax].as_long()
        solver.pop()
        
        return {
            'true_branch': f"eax == {true_result}",
            'false_branch': f"eax != {false_result}",
        }
```

**Unicorn 验证器（模拟执行验证）**：

```python
from unicorn import *
from unicorn.x86_const import *

class UnicornValidator:
    """用 Unicorn 模拟执行验证 Angr 符号执行求解结果。
    
    为什么需要：
    1. 安全测试：Angr 求解出 "输入 eax=0x12345678 触发分支 B"，
       但直接写入真实进程可能崩溃。Unicorn 在隔离环境中验证。
    2. 自修改代码：VMProtect 等保护运行时解密代码，Unicorn 模拟执行可观察解密过程。
    3. 替代硬件断点：Unicorn 可以 Hook 所有内存访问，无需真实断点。
    """
    
    def __init__(self, code_bytes: bytes, base_addr: int, arch=UC_ARCH_X86, mode=UC_MODE_64):
        self.mu = Uc(arch, mode)
        self.base_addr = base_addr
        
        # 映射代码内存
        self.mu.mem_map(base_addr, 0x10000)
        self.mu.mem_write(base_addr, code_bytes)
        
        # 映射栈内存
        self.stack_addr = 0x7FFF0000
        self.mu.mem_map(self.stack_addr, 0x10000)
        self.mu.reg_write(UC_X86_REG_RSP, self.stack_addr + 0x8000)
        
        # Hook 内存写入（替代硬件断点）
        self.mu.hook_add(UC_HOOK_MEM_WRITE, self._mem_write_hook)
        self.mem_writes = []
        
    def _mem_write_hook(self, uc, access, address, size, value, user_data):
        self.mem_writes.append({
            'addr': address,
            'value': value,
            'size': size,
        })
        
    def validate_input(self, input_state: Dict[str, int], 
                       target_addr: int) -> bool:
        """验证给定输入是否能执行到目标地址。"""
        # 设置寄存器
        for reg_name, val in input_state.items():
            reg_id = getattr(x86_const, f'UC_X86_REG_{reg_name.upper()}')
            self.mu.reg_write(reg_id, val)
        
        try:
            self.mu.emu_start(self.base_addr, target_addr)
            pc = self.mu.reg_read(UC_X86_REG_RIP)
            return pc == target_addr
        except UcError as e:
            print(f"[Unicorn] Error: {e}")
            return False
            
    def get_mem_writes(self) -> List[Dict]:
        """获取模拟执行期间的内存写入记录。"""
        return self.mem_writes
```

**Frida 动态插桩（跨平台替代方案）**：

```python
import frida

class FridaDebugger:
    """Frida 替代 Windows API 调试器，实现跨平台动态插桩。
    
    为什么用 Frida：
    1. 跨平台：Windows/Linux/macOS/Android/iOS 统一接口
    2. 函数 Hook：拦截任意函数调用，记录参数和返回值
    3. JavaScript 注入：可以注入脚本监控内存访问、修改函数行为
    4. 反调试绕过：Hook IsDebuggerPresent 等函数
    """
    
    def __init__(self):
        self.session = None
        self.scripts = {}
        
    def attach(self, pid: int):
        self.session = frida.attach(pid)
        
    def set_memory_hook(self, address: int, on_write: Callable):
        """用 Frida Interceptor 监控内存写入（替代硬件断点）。"""
        script_code = f"""
        Interceptor.attach(ptr({address}), {{
            onEnter: function(args) {{
                send({{type: 'mem_write', addr: {address}, val: args[0]}});
            }}
        }});
        """
        script = self.session.create_script(script_code)
        script.on('message', lambda msg, data: on_write(msg['payload']))
        script.load()
        self.scripts[f"mem_{address}"] = script
        
    def hook_function(self, module_name: str, func_name: str, 
                     on_call: Callable):
        """Hook 函数调用，记录参数。"""
        script_code = f"""
        var module = Process.findModuleByName('{module_name}');
        var func = Module.findExportByName('{module_name}', '{func_name}');
        Interceptor.attach(func, {{
            onEnter: function(args) {{
                send({{
                    type: 'func_call',
                    name: '{func_name}',
                    args: [args[0].toInt32(), args[1].toInt32()]
                }});
            }}
        }});
        """
        script = self.session.create_script(script_code)
        script.on('message', lambda msg, data: on_call(msg['payload']))
        script.load()
        self.scripts[f"func_{func_name}"] = script
        
    def bypass_antidebug(self):
        """绕过常见反调试检查。"""
        script_code = """
        // Hook IsDebuggerPresent
        var IsDebuggerPresent = Module.findExportByName(null, 'IsDebuggerPresent');
        Interceptor.replace(IsDebuggerPresent, new NativeCallback(function() {
            return 0;
        }, 'int', []));
        
        // Hook CheckRemoteDebuggerPresent
        var CheckRemoteDebuggerPresent = Module.findExportByName(
            null, 'CheckRemoteDebuggerPresent');
        Interceptor.replace(CheckRemoteDebuggerPresent, new NativeCallback(function(hProcess, pbDebuggerPresent) {
            Memory.writeU8(pbDebuggerPresent, 0);
            return 1;
        }, 'int', ['pointer', 'pointer']));
        """
        script = self.session.create_script(script_code)
        script.load()
        self.scripts['antidebug'] = script
```

**Capstone 多架构回退**：

```python
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_MODE_64
from capstone import CS_ARCH_ARM, CS_ARCH_ARM64, CS_ARCH_MIPS

class CapstoneFallback:
    """当 Zydis 不支持目标架构时（如 ARM64），回退到 Capstone。
    
    项目旧版 `recycle/disasm/disassembler.py` 已完整实现 Capstone 集成，
    只需将其迁移回主目录，作为多架构支持的后备引擎。
    """
    
    def __init__(self, arch='x86', mode='64'):
        arch_map = {
            'x86': CS_ARCH_X86,
            'arm': CS_ARCH_ARM,
            'arm64': CS_ARCH_ARM64,
            'mips': CS_ARCH_MIPS,
        }
        mode_map = {
            '32': CS_MODE_32,
            '64': CS_MODE_64,
        }
        self.md = Cs(arch_map[arch], mode_map[mode])
        self.md.detail = True
        
    def disassemble(self, data: bytes, address: int):
        return self.md.disasm(data, address)
```

**Angr 与动态追踪的联动流程**：

```
用户: "找到修改金币的函数"
  ↓
Agent: first_scan → 候选地址 0x7FF6A00B1234
  ↓
Agent: 在 0x7FF6A00B1234 设置写断点 → 运行游戏，花掉金币
  ↓
Debugger: 命中！EIP = 0x401000
  ↓
GhidraBridge: 查询 0x401000 所属函数 → "Player::SpendMoney"
  ↓
AngrBridge.analyze_function(0x401000, dynamic_trace=DFG):
  - Angr 构建 CFG：函数有 5 个基本块，3 条分支
  - 对比动态 DFG：只触发了 2 条分支
  - 未触发分支：用符号执行探索 → 求解触发条件
  - 结果：触发分支 3 需要 eax < 0（金币为负数）
  ↓
Z3QuickSolver: 验证分支条件（快速求解，无需完整 Angr 路径探索）
  ↓
UnicornValidator: 模拟执行验证（构造 eax=-1，验证是否确实走分支 3）
  ↓
Agent: 确认分支 3 是 "金币不足，提示购买" → 语义标注
  ↓
EvidenceAligner: 标记分支 3 为 predicted（符号执行证明可达，动态未触发）
  ↓
Agent: 询问用户 "是否测试金币不足分支？" 或直接注入金币为负数测试
```

---

### 4.3 Layer 1: 反混淆与脱壳（Deobfuscator）

**为什么必须在最底层？**
- 如果程序加壳（UPX/VMProtect），静态分析看到的代码是垃圾
- 如果存在花指令（junk code），Zydis 反汇编会错误识别指令边界
- 如果存在控制流平坦化（flattening），CFG 构建会生成虚假分支

**反混淆策略**：

```python
class Deobfuscator:
    """混淆检测与对抗引擎。"""
    
    def analyze_protection(self, module: ProcessModule) -> ProtectionProfile:
        """检测目标程序使用的保护技术。"""
        profile = ProtectionProfile()
        
        # 1. 壳检测
        profile.packer = self._detect_packer(module)
        # UPX: 特征段名 "UPX0", "UPX1"
        # VMProtect: 导入表严重损坏，IAT 被 hook
        # Themida: 特征代码片段
        
        # 2. 花指令检测
        profile.junk_code = self._detect_junk_code(module)
        # 特征：短跳转跳转到下一条指令（jmp +2）
        # 特征：条件跳转条件永远为真/假（如 xor eax, eax; jnz label）
        
        # 3. 控制流平坦化检测
        profile.flattening = self._detect_flattening(module)
        # 特征：巨大的 switch 结构（dispatcher + 大量 case）
        # 特征：所有基本块通过同一个 dispatcher 跳转
        
        # 4. 反调试检测
        profile.antidebug = self._detect_antidebug(module)
        # 特征：IsDebuggerPresent, CheckRemoteDebuggerPresent, NtQueryInformationProcess
        # 特征：Timing checks (RDTSC, QueryPerformanceCounter)
        # 特征：SEH 异常处理（故意触发异常检测调试器）
        
        return profile
        
    def deobfuscate(self, module: ProcessModule, 
                    profile: ProtectionProfile) -> DeobfuscatedModule:
        """根据检测结果选择反混淆策略。"""
        
        if profile.packer == "UPX":
            # 策略：UPX 有标准脱壳算法，可以自动脱壳
            return self._unpack_upx(module)
            
        elif profile.packer == "VMProtect":
            # 策略：VMProtect 是虚拟机保护，静态分析几乎不可能
            # 切换为纯动态分析策略：
            # 1. 在 VM 入口/出口设置断点
            # 2. 记录 VM 执行轨迹
            # 3. 用 IR 模拟 VM 指令（如果有已知 VM 模式）
            # 4. 否则标记为 "需要人工分析或专用 VM 分析器"
            return self._dynamic_vm_analysis(module)
            
        elif profile.flattening:
            # 策略：控制流平坦化还原
            # 1. 识别 dispatcher 块
            # 2. 根据实际跳转模式重建原始控制流
            # 3. 删除 dispatcher 和虚假边
            return self._deflatten(module)
            
        elif profile.junk_code:
            # 策略：花指令去除
            # 1. 识别无效/无意义指令序列
            # 2. 用 NOP 替换或删除
            # 3. 重新计算跳转目标
            return self._remove_junk(module)
            
        else:
            # 无保护，直接返回
            return DeobfuscatedModule(original=module)
```

**反调试绕过策略**：

```python
class AntiDebugBypass:
    """反调试对抗。"""
    
    def bypass(self, process: ProcessHandle, profile: ProtectionProfile):
        """根据反调试类型选择绕过策略。"""
        
        for technique in profile.antidebug:
            if technique == "IsDebuggerPresent":
                # 策略：hook PEB.IsDebugged 标志，强制返回 0
                self._patch_peb_debugged(process, value=0)
                
            elif technique == "NtQueryInformationProcess":
                # 策略：hook NtQueryInformationProcess，过滤 DebugPort 查询
                self._hook_ntquery(process)
                
            elif technique == "TimingCheck":
                # 策略：减慢目标进程执行速度，或 hook 时间查询函数
                self._slowdown_or_hook_timer(process)
                
            elif technique == "SEH":
                # 策略：设置 Vectored Exception Handler，拦截并处理异常
                self._install_veh_handler(process)
                
            elif technique == "HardwareBreakpoint":
                # 策略：检测并保护我们的硬件断点不被清除
                self._protect_hardware_breakpoints(process)
```

**保护级别与策略矩阵**：

| 保护类型 | 检测方法 | 反制策略 | 难度 |
|---------|---------|---------|------|
| UPX 加壳 | 段名特征 | 标准脱壳算法 | 简单 |
| VMProtect | 导入表损坏 | 纯动态分析 / VM 模拟 | 极难 |
| 花指令 | 短跳转模式 | 模式识别 + 指令消除 | 中等 |
| 控制流平坦化 | 巨大 switch | Dispatcher 识别 + 回边重建 | 困难 |
| 反调试 PEB | 字节扫描 | PEB 修补 | 简单 |
| 反调试 Timing | RDTSC 扫描 | 时间函数 Hook | 中等 |
| 代码加密 | 运行时解密 | 内存 Dump + 重定位 | 困难 |

---

### 4.4 Layer 4: 证据对齐算法（EvidenceAligner）

**为什么这是最难的 AI 问题？**

静态 CFG 和动态 DFG 是**两个独立的信息源**，它们往往不一致：

| 静态 CFG 声称 | 动态 DFG 观测 | 矛盾解释 |
|-------------|------------|---------|
| 函数有 5 条分支 | 只抓到 3 条 | 2 条是死代码？还是未触发？ |
| 基本块 A 可以到达 B | 动态从未观测 A→B | 是保护条件阻止？还是路径不可达？ |
| 指令 I 写入地址 X | 断点从未在 I 命中 | 是条件写入？还是地址计算错误？ |
| 动态观测到 A→C 跳转 | 静态 CFG 没有 A→C 边 | 是间接跳转未解析？还是运行时生成的代码？ |

**证据对齐算法设计**：

```python
class EvidenceAligner:
    """融合静态 CFG 和动态 DFG，生成统一的知识图谱。"""
    
    def __init__(self, cfg: CFG, dfg: DFGGraph):
        self.cfg = cfg          # 静态控制流图（完整但可能含虚假路径）
        self.dfg = dfg          # 动态数据流图（真实但碎片不完整）
        self.fused_graph = FusedGraph()
        
    def align(self) -> FusedGraph:
        """
        三阶段对齐算法：
        
        Phase 1: 节点对齐（Node Alignment）
        - 静态基本块 vs 动态指令轨迹 → 地址匹配
        - 静态函数入口 vs 动态调用栈帧 → 符号匹配
        - 结果：每个静态节点标记为 confirmed / predicted / dead / unknown
        
        Phase 2: 边一致性检验（Edge Consistency Check）
        - 对于每条静态边 A→B：
          a. 动态观测到 A→B：标记 confirmed，置信度 = 命中次数 / 总运行次数
          b. 动态从未观测 A→B：
             - 如果 A 是条件分支：标记 predicted（需要符号执行求解触发条件）
             - 如果 A 是间接跳转：标记 unresolved（需要更深入的静态分析）
             - 如果 A 是调用且被调函数从未返回：标记 suspicious（可能是反调试陷阱）
          c. 动态观测到 A→C 但静态没有 A→C 边：
             - 标记 dynamic_only（运行时代码生成、 unpacker、 或静态分析错误）
        
        Phase 3: 置信度传播与冲突消解（Confidence Propagation & Conflict Resolution）
        - 基于图神经网络（GNN）或启发式规则传播置信度
        - 冲突消解：
          a. 静态说"可达"，动态说"不可达"，符号执行说"不可达" → 标记 dead_code
          b. 静态说"不可达"，动态说"可达" → 标记 dynamic_generated（运行时生成）
          c. 静态说"可达"，动态说"不可达"，符号执行说"可达" → 标记 hard_to_trigger（需要特定输入）
        """
        
        # 节点对齐
        self._align_nodes()
        
        # 边一致性检验
        self._check_edge_consistency()
        
        # 置信度传播（可选 GNN）
        self._propagate_confidence()
        
        # 冲突消解
        self._resolve_conflicts()
        
        return self.fused_graph
        
    def _align_nodes(self):
        """将动态观测的指令与静态基本块对齐。"""
        for dynamic_insn in self.dfg.get_executed_instructions():
            addr = dynamic_insn.address
            # 找到包含该地址的静态基本块
            static_block = self.cfg.find_block_containing(addr)
            if static_block:
                self.fused_graph.add_node_mapping(
                    static_id=static_block.id,
                    dynamic_id=dynamic_insn.id,
                    status="confirmed",
                    confidence=1.0
                )
            else:
                # 动态观测到静态 CFG 中没有的指令
                self.fused_graph.add_orphan_dynamic_node(
                    dynamic_insn,
                    possible_reasons=["runtime_generated", "unpacker", "static_analysis_error"]
                )
                
    def _check_edge_consistency(self):
        """检验静态边与动态边的一致性。"""
        for static_edge in self.cfg.edges:
            src, dst = static_edge.source, static_edge.target
            dynamic_hits = self.dfg.get_transition_count(src, dst)
            
            if dynamic_hits > 0:
                static_edge.status = "confirmed"
                static_edge.confidence = min(1.0, dynamic_hits / 10)  # 10 次命中 = 100% 置信
            else:
                # 从未动态观测到
                if static_edge.type == "conditional":
                    static_edge.status = "predicted"
                    static_edge.confidence = 0.5  # 需要符号执行验证
                elif static_edge.type == "indirect":
                    static_edge.status = "unresolved"
                    static_edge.confidence = 0.3
                else:
                    static_edge.status = "unverified"
                    static_edge.confidence = 0.5
                    
    def _resolve_conflicts(self):
        """消解静态与动态之间的冲突。"""
        for node in self.fused_graph.nodes:
            static_reachable = self.cfg.is_reachable_from_entry(node)
            dynamic_observed = self.dfg.was_executed(node)
            
            if static_reachable and not dynamic_observed:
                # 静态说可达，动态说不可达
                if node.has_symbolic_path:
                    # 符号执行证明可达 → 需要特定输入
                    node.status = "hard_to_trigger"
                    node.recommended_action = "symbolic_execution"
                else:
                    # 符号执行证明不可达 → 死代码
                    node.status = "dead_code"
                    node.recommended_action = "ignore"
                    
            elif not static_reachable and dynamic_observed:
                # 静态说不可达，动态说可达 → 运行时生成
                node.status = "runtime_generated"
                node.recommended_action = "dynamic_only_analysis"
```

**融合后的图结构（FusedGraph）**：

```python
class FusedGraph:
    """静态 + 动态 + 符号执行 融合后的统一知识图谱。"""
    
    nodes: Dict[str, FusedNode]
    edges: Dict[str, FusedEdge]
    
class FusedNode:
    """融合节点：一个静态基本块 + 0 或多个动态观测。"""
    address: int
    static_block: Optional[BasicBlock]      # 静态 CFG 中的块
    dynamic_hits: List[DynamicExecution]      # 动态观测记录
    
    # 对齐状态
    status: NodeStatus  # confirmed / predicted / dead_code / hard_to_trigger / runtime_generated / unknown
    confidence: float   # 0.0-1.0
    
    # 来源证据
    evidence: List[Evidence]
    # - StaticEvidence: 静态分析发现
    # - DynamicEvidence: 断点/追踪命中
    # - SymbolicEvidence: 符号执行证明
    
    # 推荐行动
    recommended_action: str
    # - "confirmed": 无需进一步分析
    # - "symbolic_execution": 需要符号执行求解触发条件
    # - "dynamic_trigger": 需要构造特定输入触发
    # - "ignore": 死代码，无需分析
    # - "dynamic_only_analysis": 纯动态分析（运行时生成代码）
    
class FusedEdge:
    """融合边：静态边 + 动态转移观测。"""
    source: str
    target: str
    type: EdgeType  # call / jump / conditional_true / conditional_false / indirect / data_flow
    
    # 对齐状态
    status: EdgeStatus  # confirmed / predicted / unverified / dynamic_only / suspicious
    confidence: float
    
    # 动态统计
    hit_count: int
    last_hit: float
    
    # 条件谓词（如果是条件边）
    predicate: Optional[IRPredicate]
    # 符号执行求解的输入条件
    triggering_input: Optional[Dict[str, int]]
```

**与 LLM 的集成**：

```python
def generate_alignment_report(aligner: EvidenceAligner) -> str:
    """生成融合后的对齐报告，供 LLM 分析。"""
    
    report = f"""
    # 证据对齐报告
    
    ## 已确认路径（{len(aligner.confirmed_paths)} 条）
    这些路径已被动态追踪验证，可直接用于分析：
    {aligner.confirmed_paths}
    
    ## 待验证路径（{len(aligner.predicted_paths)} 条）
    静态分析发现但动态未触发，需要进一步验证：
    {aligner.predicted_paths}
    推荐行动：符号执行求解输入条件
    
    ## 死代码（{len(aligner.dead_code)} 块）
    静态声称可达但符号执行证明不可达，可能是反调试陷阱或编译器残留：
    {aligner.dead_code}
    推荐行动：忽略
    
    ## 运行时生成代码（{len(aligner.runtime_generated)} 块）
    动态观测到但静态不存在，可能是加壳/自修改代码：
    {aligner.runtime_generated}
    推荐行动：纯动态分析
    
    ## 冲突摘要
    {aligner.conflict_summary}
    """
    
    return report
```

---

## 5. 更新后的完整数据流（含新层）

```
用户输入: "找到修改金币的函数"
  ↓
Layer 6 (IntentAgent)
  ↓
Layer 5 (上下文管理)
  ↓
Layer 2 (Ghidra 分析层) ── 如果检测到保护 → 先调用 Layer 1 (Deobfuscator)
  ↓
Layer 1 (Deobfuscator) ── 检测 UPX/VMProtect/花指令/平坦化
  ├─ 有保护 → 脱壳/反混淆/切换动态策略
  └─ 无保护 → 继续
  ↓
Layer 2 (ProcessAnalyzer) ── 分析进程结构（模块/段/字符串）
  ↓
Layer 3 (Scanner) ── 扫描内存找到金币地址
  ↓
Layer 3 (Debugger) ── 设置写断点，捕获命中
  ↓
Layer 3 (AngrBridge) ── 构建命中函数 CFG + 符号执行探索未触发分支
  ├─ CFGFast: 函数有 5 个基本块，3 条分支（含间接跳转解析）
  ├─ SimulationManager: 探索未触发分支 → 求解触发条件（eax < 0）
  └─ Claripy (Z3): 求解具体输入值 → 返回 {eax: -1}
  ↓
Layer 3 (UnicornValidator) ── 模拟执行验证（构造 eax=-1，验证是否触发分支 3）
  ↓
Layer 4 (EvidenceAligner) ── 融合静态 CFG + 动态 DFG + 符号执行结果
  ├─ 标记 confirmed / predicted / dead / runtime_generated
  └─ 生成对齐报告
  ↓
Layer 2 (GhidraBridge) ── 查询断点命中地址的 Ghidra 函数/反编译代码
  ↓
Layer 2 (PCodeTranslator) ── 将 P-Code 翻译为带实时值的语义描述
  ↓
Layer 2 (DecompilerBridge) ── 生成增强伪 C 代码（注入动态寄存器值）
  ↓
Layer 6 (LLM) ── "这是金币更新函数，逻辑是：读取当前值→加5→如果达到100则触发上限检测"
  ↓
Layer 6 (用户) ── 显示结果 + 确认/追问
  ↓
Layer 4 (SQLite) ── 保存发现到知识图谱（修正 Ghidra 结构体定义）
```

---

## 6. 修正后的开发路线图

### Phase 0: 基础修复（✅ 完成）
- [x] 64 位模块地址修复
- [x] ReAct → Act 模式重构
- [x] 工具结果外部化 + 上下文压缩
- [x] 极简 system prompt（< 800 tokens）
- [x] 进程切换自动刷新
- [x] LLM 错误恢复（WAITING_USER 而非 break）

### Phase 1: 存储层实现（进行中）
- [ ] `ReverseEngineeringGraph` SQLite 类
- [ ] 四分层表结构（nodes/edges/node_semantics/findings/key_registry）
- [ ] `SchemaGovernor` 寿命治理引擎
- [ ] AgentContext 自动写入 findings
- [ ] 进程切换时自动加载历史项目
- [ ] LLM prompt 动态注入已知语义

### Phase 2: Ghidra 集成层（🔴 致命缺口）
- [ ] **GhidraBridge**: Headless 调用封装（analyzeHeadless 命令行调用）
- [ ] **内存镜像导出**: 附加进程时导出主模块内存到文件
- [ ] **分析结果导入**: Ghidra JSON 输出解析 + SQLite 知识库导入
- [ ] **实时查询**: 动态断点命中时查询 Ghidra 知识库（地址 → 函数/反编译/P-Code）
- [ ] **PCodeTranslator**: P-Code 简化翻译（供 LLM 理解，无需自研 IR）
- [ ] **DecompilerBridge**: 反编译代码 + 动态寄存器值注入（增强型 LLM 提示）
- [ ] **结构体动态修正**: 对比 Ghidra 静态推断与动态访问，自动扩展结构体
- [ ] **Ghidra 导入脚本生成**: 修正后的结构体 → v2_ghidra_import_*.java

### Phase 3: 开源工具集成（🔴 致命缺口）
- [ ] **Angr 安装与封装**: `pip install angr` + `AngrBridge` 桥接层
- [ ] **Angr CFG 导入**: 调用 `CFGFast` 构建函数级 CFG，导入 SQLite 知识库
- [ ] **Angr 符号执行**: `SimulationManager` 路径探索，结合动态追踪种子引导
- [ ] **Angr 约束求解**: Claripy (Z3 封装) 求解触发条件 → 具体输入值
- [ ] **Angr ↔ 动态联动**: 对比动态 DFG 与 Angr CFG，识别未触发分支
- [ ] **Z3 独立集成**: `pip install z3-solver` + `Z3QuickSolver` 基本块级快速求解
- [ ] **Unicorn 集成**: `pip install unicorn` + `UnicornValidator` 模拟执行验证
- [ ] **Frida 集成**: `pip install frida-tools` + `FridaDebugger` 跨平台动态插桩
- [ ] **Capstone 回退**: `pip install capstone` + 多架构反汇编支持 (ARM64/MIPS)
- [ ] **自研边界明确**: Angr 做符号执行/CFG/Z3，我们只写桥接层、融合层、Agent 层

### Phase 4: 自研模块（基于开源工具之上）
- [ ] **AngrBridge**: 动态追踪数据 → Angr 初始状态（种子引导），缩小搜索空间
- [ ] **UnicornValidator**: Angr 求解结果 → 模拟执行验证（安全测试）
- [ ] **FridaDebugger**: Frida 封装为与现有 `Debugger` 相同的接口（跨平台）
- [ ] **EvidenceAligner**: 三源融合（Ghidra/Angr 静态 + 动态 DFG + 符号执行结果）
- [ ] **SchemaGovernor**: 语义标签寿命治理、LLM prompt 动态注入
- [ ] **PCodeTranslator**: Ghidra P-Code → 简化语义描述（供 LLM 理解）
- [ ] **DecompilerBridge**: 反编译代码 + 动态寄存器值注入（增强型 LLM 提示）

### Phase 5: 反混淆与脱壳（🟠 严重缺口）
- [ ] **PackerDetector**: UPX / VMProtect / Themida 检测
- [ ] **UPX 脱壳**: 标准算法自动脱壳
- [ ] **JunkCodeDetector**: 花指令模式识别
- [ ] **JunkCodeRemover**: 无效指令消除
- [ ] **FlatteningDetector**: 控制流平坦化检测
- [ ] **Deflattening**: Dispatcher 识别 + 原始控制流重建
- [ ] **AntiDebugDetector**: IsDebuggerPresent / NtQuery / Timing / SEH 检测
- [ ] **AntiDebugBypass**: PEB 修补 / 时间函数 Hook / VEH 拦截
- [ ] **VMProtect 策略**: 纯动态分析 / VM 模拟（标记为极难）

### Phase 6: 证据对齐算法（🟠 严重缺口）
- [ ] **NodeAligner**: 静态基本块 ↔ 动态指令轨迹对齐
- [ ] **EdgeConsistencyChecker**: 静态边 ↔ 动态转移一致性检验
- [ ] **ConfidencePropagator**: 置信度传播（启发式或 GNN）
- [ ] **ConflictResolver**: 死代码 / 运行时生成 / 难以触发分支判定
- [ ] **FusedGraph**: 统一融合图结构（confirmed/predicted/dead/runtime_generated）
- [ ] **AlignmentReport**: LLM 可理解的对齐报告生成
- [ ] **ActionRecommender**: 根据对齐状态推荐下一步行动

### Phase 7: 分析引擎完善
- [ ] 硬件断点完整实现（写入/读取/执行）
- [ ] 调用栈重建（最多 8 层）
- [ ] 指令级污点分析（简化版）
- [ ] 结构体推断自动化（从偏移聚类到字段命名）

### Phase 8: 可视化与报告
- [ ] 交互式 DFG/CFG/IR 图编辑（ECharts）
- [ ] 结构体定义导出（C header / Python dataclass）
- [ ] 逆向报告生成（Markdown + 证据链）
- [ ] 跨会话对比（版本演进检测）

### Phase 9: 高级功能
- [ ] 多 Agent 协作（并行分析不同模块）
- [ ] 模式识别引擎（每帧调用/事件触发/定时器）
- [ ] Ghidra 插件集成（导出到 Ghidra 分析）
- [ ] 网络/文件 IO 分析扩展

---

## 7. 关键设计决策总结

### 7.1 为什么 P-Code 翻译层必须独立于架构？

```
Zydis 输出 (x86):        Ghidra P-Code:           PCodeTranslator 输出:    LLM 看到:
mov eax, [rbx+0x10]   →   LOAD $U0 = [RBX+0x10]  →  "读取 [RBX+0x10] 的 int32"  →  "读取 player->health"
add eax, 5            →   INT_ADD EAX = $U0 + 5   →  "加 5"                    →  "加 5"
cmp eax, 100          →   INT_EQUAL $U1 = EAX==100 →  "比较是否等于 100"        →  "比较是否等于 100"
jz 0x1234            →   CBRANCH 0x1234, $U1    →  "如果等于则跳转 0x1234"    →  "如果等于，跳转到上限处理"
```

没有 P-Code 翻译层，LLM 必须直接理解 x86 汇编或 Ghidra 的原始 P-Code（对 LLM 过于复杂）。P-Code 翻译层将 Ghidra 的 IR 转化为 LLM 可直接理解的简化语义描述，使上层分析**完全不需要知道 CPU 架构**。

Ghidra 本身已支持 x86/ARM64/RISC-V 到 P-Code 的翻译，我们无需自研 IR，只需在 P-Code 之上加一层**简化语义翻译**（PCodeTranslator）。

### 7.2 为什么用 Angr 而不是自研符号执行 + CFG？

**自研 vs 开源工具对比：**

| 维度 | 自研 SymbolicExecutor + StaticCFGBuilder | Angr (开源) |
|------|----------------------------------------|-------------|
| 开发成本 | 6-12 个月（全职团队，10 万+ 行代码） | `pip install angr`（已存在，100 万+ 行代码） |
| 功能完整度 | 基本块级，x86 only | 函数级/程序级，x86/ARM/MIPS/PowerPC/... |
| 间接跳转解析 | 需自行实现 heuristics（错误率高） | `CFGFast` 自动解析（10 年+ 优化） |
| 路径爆炸处理 | 无策略（复杂函数直接崩溃） | 内置 DFS/BFS/循环限制/路径合并 |
| 约束求解 | 需手动集成 Z3（API 复杂） | 内置 Claripy（Z3 高级封装） |
| 系统调用模拟 | 需自行实现（每个 syscall 都要写） | 内置 200+ SimProcedures |
| 真实案例验证 | 0 个（未上线） | 10 年+ CTF/学术/工业验证（DARPA CGC 冠军） |
| 许可证 | N/A | LGPL（允许集成和修改） |

**结论：自研没有任何理由。**

- 不是做学术研究（发论文），不需要"新颖性"
- 不是教学项目（练手），需要工程可靠性
- Angr 是 UC Santa Barbara 的 Shellphish 团队（CTF 世界冠军团队）维护的工业级框架
- 我们的自研价值是**桥接层**（AngrBridge）：将动态追踪数据作为 Angr 的种子引导，将 Angr 结果与动态追踪融合

**Angr 在 MemoryGraph 中的角色：**

```
MemoryGraph 动态追踪 → 断点命中 → 获取 EIP/寄存器/调用栈
  ↓
AngrBridge: 将 EIP 所在函数加载到 Angr
  - 以动态寄存器值为初始状态（种子引导）
  - 调用 Angr 的 CFGFast 构建函数 CFG
  - 调用 Angr 的 SimulationManager 探索未触发分支
  - 调用 Angr 的 Claripy 求解触发条件
  ↓
Angr 输出: {未触发分支: 3 条, 触发条件: {eax: -1}, 求解时间: 0.5s}
  ↓
UnicornValidator: 模拟执行验证（构造 eax=-1，验证是否触发）
  ↓
EvidenceAligner: 融合 Angr 静态 + 动态 DFG → 标记 confirmed/predicted
```

**自研边界：**
- ✅ **我们做**：AngrBridge（数据桥接）、UnicornValidator（验证封装）、FridaDebugger（跨平台封装）、EvidenceAligner（三源融合）
- ❌ **不做**：符号执行引擎、CFG 构建算法、约束求解器、系统调用模拟器（Angr 已完整实现）

---

### 7.3 为什么反混淆必须在最底层？

```
原始代码 → [加壳/花指令/平坦化] → 混淆代码
                 ↑
            Deobfuscator (Layer 1)
                 ↓
干净代码 → GhidraBridge (Layer 2) → 导入静态函数/反编译/结构体
              ↓
         动态断点命中时查询 Ghidra 知识库
              ↓
         PCodeTranslator (Layer 2) → 简化 P-Code 语义描述
              ↓
         DecompilerBridge (Layer 2) → 增强伪 C 代码（注入动态值）
              ↓
         AngrBridge (Layer 3) → 验证/补全 Ghidra 的 CFG (CFGFast + 符号执行)
              ↓
         ...
```

如果反混淆在 P-Code 翻译层之后：
- PCodeTranslator 看到花指令 → 翻译出无意义的语义描述 → 上层分析崩溃
- Angr CFGFast 看到平坦化代码 → 生成虚假分支 → 符号执行求解无意义约束
- 反混淆必须在**最底层**（内存镜像导出到 Ghidra 之前），或 Ghidra 分析后手动标记混淆区域

### 7.4 为什么证据对齐需要融合三源信息？

```
静态 CFG: "函数有 5 条分支"
动态 DFG: "只抓到 3 条"
符号执行: "证明第 4 条可达，第 5 条不可达"

融合结果：
- 3 条 confirmed（动态验证）
- 1 条 predicted（符号执行证明可达，但未触发）→ 推荐构造输入触发
- 1 条 dead_code（符号执行证明不可达）→ 忽略
```

没有融合算法：
- 静态说 5 条，动态说 3 条 → 矛盾，不知道信谁
- 可能把死代码当成功能分支分析（浪费资源）
- 可能把未触发分支当成死代码忽略（漏掉关键逻辑）

---

**文档更新结束。本次补充：
- 5 个致命缺口声明
- 修正后的 7 层架构图（含 IR、CFG、符号执行、反混淆、证据对齐）
- 各层详细设计（数据结构、算法、示例）
- 更新后的完整数据流
- 修正后的 8 阶段开发路线图**


### 4.1 IntentAgent — Act 模式交互引擎

**架构演进**：ReAct → Act（基于 AgentBoard NeurIPS 2024 论文）

| 特性 | ReAct (旧) | Act (新) |
|------|-----------|----------|
| LLM 输出 | `<思考>分析</思考><行动>JSON</行动>` | `<行动>JSON</行动>` 或 `<回复>文本</回复>` |
| 上下文消耗 | 每轮 200-500 tokens thought | 无 thought，节省 30-50% tokens |
| 适用场景 | 14B+ 模型 | 4B-9B 小模型 |
| 长交互表现 | 30 轮后 context 爆炸 | 30 轮后仍稳定 |

**核心组件**：

```python
class IntentAgent:
    # 状态机
    state: AgentState (IDLE → ANALYZING → WAITING_USER → THINKING → RUNNING_TOOL → DONE)
    
    # 上下文管理
    _context: AgentContext          # 工具结果外部化缓存
    _conversation_history: List[Dict] # LLM 对话历史（仅摘要+引用）
    
    # 工具执行
    _execute_tool(tool_name, params) → result
    _tool_results_cache: Dict[str, Dict]  # 完整结果卸载存储
    
    # 解析器
    _parse_llm_response(text) → (thought, action)
    # 只解析 <行动>JSON</行动> 或 <回复>文本</回复>
```

**工具结果外部化**：

```python
class AgentContext:
    _tool_results_cache: Dict[str, Dict] = {}  # 完整结果存储
    _tool_result_counter = 0

    def store_tool_result(self, tool_name, result) -> str:
        # 生成 ref key
        key = f"{tool_name}_{counter}_{timestamp}"
        self._tool_results_cache[key] = result
        # LRU 淘汰：最多保留 50 条
        if len(self._tool_results_cache) > 50:
            del oldest
        return key
```

**History 中只存**：`[Tool Result] disassemble: 20条指令 [ref: disassemble_1_123456]`
**完整结果存**：`_tool_results_cache`，按需检索

### 4.2 上下文压缩三阶段

```
Phase 1: 工具结果卸载 (Tool Result Offloading)
  触发：工具结果 > 20K tokens
  动作：完整结果存入 cache，history 只存摘要
  
Phase 2: 输入参数卸载 (Input Parameter Offloading)
  触发：多轮扫描后候选地址列表膨胀
  动作：参数列表哈希化，history 只存 "[addr_list: hash_abc123]"
  
Phase 3: 总结压缩 (Summary Compression)
  触发：总 tokens > 75% 预算
  动作：将早期历史轮次压缩为单条摘要
  触发：总 tokens > 90% 预算
  动作：更激进压缩，仅保留核心发现
```

### 4.3 已暴露工具列表

| 工具 | 参数 | 用途 | 风险等级 |
|------|------|------|----------|
| `first_scan` | `(type, value)` | 首次内存扫描 | 只读 |
| `next_scan` | `(filter, value)` | 下次扫描（缩小范围） | 只读 |
| `read_memory` | `(addr, size)` | 读取内存字节 | 只读 |
| `disassemble` | `(addr, count=20)` | 反汇编指令 | 只读 |
| `disassemble_region` | `(start, end)` | 反汇编范围 | 只读 |
| `find_pattern` | `(hex)` | 内存特征码搜索 | 只读 |
| `set_breakpoint` | `(addr, size, mode)` | 设置硬件/内存断点 | 监控 |
| `get_breakpoint_hits` | `(limit)` | 获取断点命中记录 | 只读 |
| `resolve_pointer` | `(base, offsets)` | 多级指针解引用 | 只读 |
| `write_memory` | `(addr, value, type)` | 修改内存值 | **危险** |
| `ask_user` | `(question)` | 询问用户 | 交互 |
| `refresh_analysis` | `()` | 刷新进程分析 | 只读 |
| `finish` | `(summary)` | 完成会话 | 结束 |

### 4.4 自主级别

| 级别 | 可用工具 | 确认策略 |
|------|----------|----------|
| `full_auto` | 全部工具 | 无需确认 |
| `semi_auto` | 扫描/读取可用，写入需确认 | 写入前弹窗确认 |
| `interactive` | 读取/反汇编/ask 可用，扫描/写入需确认 | 扫描和写入都需确认 |

---

## Layer 5: 压缩与记忆层

### 5.1 三层压缩架构（MemGPT-Style）

```
┌────────────────────────────────────────────────────────────────────┐
│                    Context Window (Context RAM)                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                │
│  │  Core Prompt │ │  Compressed  │ │  Recent Turns│                │
│  │  (任务定义)   │ │  Memory (B)  │ │  (未压缩原始) │                │
│  │  ~500 tokens │ │  ~1500 tokens│ │  ~2000 tokens│                │
│  └──────────────┘ └──────────────┘ └──────────────┘                │
│  Total: 4K context (适合 4B 模型)                                  │
└────────────────────────────────────────────────────────────────────┘
                              │
                              │ Trigger (60% threshold)
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                  Compression Engine (LLM Loop)                      │
│  1. 读取 Recent Turns → 完整原始内容                                 │
│  2. 调用 LLM 对历史进行摘要压缩                                      │
│  3. 合并到 Compressed Memory                                         │
│  4. 清空 Recent Turns → 从压缩后内容继续                             │
└────────────────────────────────────────────────────────────────────┘
```

### 5.2 压缩策略

| 策略 | 触发条件 | 压缩后形式 |
|------|----------|-----------|
| **工具结果卸载** | 结果 > 20K tokens | 摘要 + `[ref: key]` 引用 |
| **输入参数卸载** | 地址列表 > 100 条 | 哈希标识 + 数量统计 |
| **步骤折叠** | 连续 3+ 次相同工具调用 | 合并为单条摘要 |
| **数值替换** | 大量字节/数值数据 | 前 3 个 + 省略号 + 后 3 个 |
| **机械膨胀去除** | 重复性模板输出 | 模式识别 + 变量替换 |

---

## Layer 4: 图构建与证据对齐层（内存 → 待持久化）

### 6.1 当前状态：纯内存

| 组件 | 存储方式 | 生命周期 | 问题 |
|------|----------|----------|------|
| `DFGGraph` | 内存对象 | 进程切换时重置 | 会话丢失 |
| `MemoryRelationshipGraph` | 内存对象 | 进程切换时重置 | 会话丢失 |
| `AgentContext.findings` | 内存列表 | 进程切换时重置 | 会话丢失 |
| `state.g_dfg` | 全局变量 | 进程切换时置 None | 会话丢失 |

### 6.2 目标：四分层存储架构（SQLite）

**设计哲学**：核心固定，语义开放，寿命治理。

```
┌────────────────────────────────────────────────────────────────────┐
│ Layer 0: 核心本体 (Hard-coded)                                     │
│ 基于 OS/CPU/编译器理论，逆向工程"物理定律"，永不改变               │
│ 节点: process, module, segment, function, basic_block, instruction│
│ 边: contains, calls, jumps_to, falls_through, reads, writes        │
│                                                                    │
│ Layer 1: 结构推导 (Semi-open)                                      │
│ 从静态/动态分析推导的程序语法结构，类型固定但字段名开放            │
│ struct, union, vtable, array, callback_table                       │
│                                                                    │
│ Layer 2: 语义标注 (Fully open, EAV)                               │
│ 运行时语义推断，完全开放，Agent 自由标注，自动治理                  │
│ "health", "gold", "license_key", "player_ptr"...                   │
│                                                                    │
│ Layer 3: 临时发现 ( findings, TTL)                                  │
│ 单次会话的临时推导，带 TTL，引用计数决定去留                        │
│ active → confirmed → promoted(L2) / rejected / expired            │
└────────────────────────────────────────────────────────────────────┘
```

### 6.3 数据模型

#### 节点表（Layer 0 + 1）

```sql
CREATE TABLE nodes (
    id          TEXT PRIMARY KEY,      -- "{project}:{type}:{addr}"
    project     TEXT NOT NULL,          -- 项目标识
    type        TEXT NOT NULL,           -- Layer 0: process/module/segment/function/bb/instruction/register
                                        -- Layer 1: struct/union/vtable/array/callback_table
    name        TEXT,
    address     INTEGER,                -- 内存地址或 RVA
    size        INTEGER,
    properties  TEXT,                   -- JSON: {disasm, bytes, confidence, ...}
    tree_path   TEXT,                   -- 树路径: "/process/module/segment/function"
    created_at  REAL                    -- timestamp
);
CREATE INDEX idx_nodes_tree ON nodes(project, tree_path);
```

#### 边表（图关系）

```sql
CREATE TABLE edges (
    id          TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    source      TEXT NOT NULL REFERENCES nodes(id),
    target      TEXT NOT NULL REFERENCES nodes(id),
    type        TEXT NOT NULL,          -- call/jump/data_flow/control_flow/pointer_deref/struct_field/weak_binding
    properties  TEXT,                   -- JSON: {offset, size, confidence, evidence}
    created_at  REAL
);
CREATE INDEX idx_edges_project ON edges(project, source, target);
```

#### 语义标注表（Layer 2，EAV）

```sql
CREATE TABLE node_semantics (
    id          INTEGER PRIMARY KEY,
    project     TEXT,
    node_id     TEXT NOT NULL,
    key         TEXT NOT NULL,           -- 开放: "health", "gold", "license_key"
    value       TEXT,                   -- 开放
    value_type  TEXT DEFAULT 'string',  -- string/int/float/json/address
    confidence  REAL,
    source      TEXT,                   -- first_scan/breakpoint/pattern_match/llm_inference
    session_id  TEXT,
    first_seen  REAL,
    last_seen   REAL,
    use_count   INTEGER DEFAULT 1,      -- 寿命核心指标
    promoted    INTEGER DEFAULT 0,      -- 是否被提升为核心
    FOREIGN KEY (node_id) REFERENCES nodes(id)
);
CREATE INDEX idx_semantics_lifetime ON node_semantics(project, last_seen, use_count);
```

#### 临时发现表（Layer 3，TTL）

```sql
CREATE TABLE findings (
    id          INTEGER PRIMARY KEY,
    project     TEXT,
    node_id     TEXT,
    finding_type TEXT,                  -- value_scan/breakpoint_hit/struct_infer/pointer_chain/pattern_match
    evidence    TEXT,                  -- JSON 原始证据
    confidence  REAL,
    tool        TEXT,
    session_id  TEXT,
    timestamp   REAL,
    ttl_hours   INTEGER DEFAULT 168,    -- 7 天默认
    referenced_by INTEGER DEFAULT 0,    -- 被引用次数
    status      TEXT DEFAULT 'active'   -- active/confirmed/rejected/expired
);
CREATE INDEX idx_findings_node ON findings(project, node_id);
```

#### 语义标签注册表（治理元数据）

```sql
CREATE TABLE key_registry (
    key         TEXT PRIMARY KEY,
    first_seen  REAL,
    last_seen   REAL,
    use_count   INTEGER DEFAULT 0,      -- 跨项目总使用次数
    project_count INTEGER DEFAULT 0,     -- 在多少项目中出现过
    avg_confidence REAL,
    promoted_to_core INTEGER DEFAULT 0,  -- 是否被提升为核心标签
    -- 如果 promoted=1，该 key 自动注入 LLM system prompt
);
```

### 6.4 寿命治理机制

| 条件 | 动作 | 结果 |
|------|------|------|
| `use_count > 50` 且 `project_count > 3` 且 `avg_confidence > 0.8` | **Promote** | 标记 `promoted_to_core=1`，注入 LLM prompt |
| `last_seen < now() - 90 days` 且 `use_count < 5` | **Demote** | 标记 `deprecated`，不再向 LLM 展示 |
| 从未被 findings 引用 | **Expire** | 物理删除或归档到冷存储 |
| 高 confidence + 多次引用 | **Confirm** | 从 L3 提升为 L2 语义标注 |

### 6.5 树与图的联合查询

```sql
-- Q1: 树查询 — 某模块下所有导出函数
SELECT * FROM nodes
WHERE project = 'notepad_3684'
  AND tree_path LIKE '/process/kernel32.dll/%'
  AND type = 'function';

-- Q2: 图查询 — 所有写入 0x1234ABCD 的指令
SELECT source, properties FROM edges
WHERE project = 'notepad_3684'
  AND target = 'notepad_3684:instruction:0x1234ABCD'
  AND type = 'write';

-- Q3: 树+图联合 — "Health" 结构体被哪些函数修改
WITH health_struct AS (
    SELECT id FROM nodes
    WHERE project = 'notepad_3684' AND name = 'Health'
)
SELECT DISTINCT n.tree_path, e.source, e.properties
FROM edges e
JOIN nodes n ON e.source = n.id
WHERE e.target IN health_struct
  AND e.type = 'write';

-- Q4: 语义溯源 — 某个标注的推断证据链
SELECT f.evidence, f.tool, f.timestamp, f.confidence
FROM findings f
JOIN node_semantics ns ON f.node_id = ns.node_id
WHERE ns.key = 'health'
ORDER BY f.timestamp;
```

### 6.6 与 LLM 的动态集成

```python
class SchemaGovernor:
    def get_prompt_injection(self, project_id: str) -> str:
        """生成动态注入 LLM system prompt 的语义上下文。"""
        # 查询高置信度语义标签
        semantics = self._db.query("""
            SELECT node_id, key, value, confidence
            FROM node_semantics
            WHERE project = ? AND confidence > 0.8
            ORDER BY use_count DESC
            LIMIT 20
        """, (project_id,))
        
        # 格式化为 LLM 可读文本
        lines = ["本项目已确认语义标签（可直接引用）："]
        for s in semantics:
            lines.append(f"- {s.node_id}: {s.key} = {s.value} (置信度 {s.confidence:.2f})")
        return "\n".join(lines)

# 在 _build_system_prompt 中注入
base = "你是Windows逆向助手。工具: ..."
semantics = self._context._schema_governor.get_prompt_injection(self.project_id)
if semantics:
    base += f"\n\n{semantics}"
```

---

## Layer 3: 分析层

### 7.1 ProcessAnalyzer（自顶向下）

```python
def analyze_process(h_process, pid, exe_path) -> Dict:
    """
    输出树形结构:
    {
        "process": {
            "pid": 3684,
            "total_modules": 42,
            "total_heap_mb": 128.5,
        },
        "main_module": {
            "name": "game.exe",
            "base": "0x7FF6A0000000",
            "size_mb": 45.2,
            "segments": [
                {"name": ".text", "base": "0x7FF6A0010000", "size": 0x123456},
                {"name": ".data", "base": "0x7FF6A0134560", "size": 0x7890},
            ],
            "exports": [...],
            "imports": [...],
        }
    }
    """
```

### 7.2 Scanner（自底向上起点）

```python
# 首次扫描
candidates = first_scan_exact(value=100, value_type=2)  # float
# 返回: [{"address": "0x1234ABCD", "value": 100.0, "type": "float"}, ...]

# 下次扫描（缩小范围）
candidates = next_scan_general(filter_type="changed", value=None)
# 返回: 在上次候选中筛选变化/增加/减少/不变/精确值
```

### 7.3 Debugger（断点追踪）

```python
# 设置硬件断点（写入监控）
breakpoint_id = set_hardware_breakpoint(
    address="0x1234ABCD",
    size=4,           # 4 bytes
    mode="write"      # 只在写入时触发
)

# 获取命中记录
hits = get_breakpoint_hits(breakpoint_id, limit=100)
# 返回: [{"eip": "0x7FF6A0023456", "registers": {...}, "stack": [...]}, ...]
```

### 7.4 64 位模块地址修复

**问题**：`CreateToolhelp32Snapshot` 在 64 位进程上返回 32 位截断地址（`OverflowError`）
**修复**：改用 `EnumProcessModulesEx` + `GetModuleInformation`（psapi）

```python
EnumProcessModulesEx = ctypes.windll.psapi.EnumProcessModulesEx
EnumProcessModulesEx.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.c_void_p,
    ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.wintypes.DWORD),
    ctypes.wintypes.DWORD,
]

class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", ctypes.wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]
```

### 7.5 AngrBridge（开源工具集成）

> **核心原则**：不重复造轮子。Angr 已完整实现符号执行 + 静态 CFG + 约束求解（Z3/Claripy）。我们只写桥接层，将动态追踪数据作为 Angr 的种子引导。

**Angr 在分析层中的角色**：

```python
import angr
import claripy

class AngrBridge:
    """桥接 Angr 与 MemoryGraph 动态追踪。"""
    
    def __init__(self, module_dump_path: str):
        self.project = angr.Project(
            module_dump_path,
            load_options={'auto_load_libs': False}
        )
        self.cfg = None
        
    def build_cfg(self, force_rebuild=False) -> angr.analyses.CFGFast:
        """构建静态 CFG（含间接跳转解析）。"""
        if self.cfg is not None and not force_rebuild:
            return self.cfg
        self.cfg = self.project.analyses.CFGFast(
            normalize=True,
            force_complete_scan=True,
            resolve_indirect_jumps=True,
        )
        return self.cfg
        
    def analyze_function(self, func_addr: int,
                         dynamic_trace: Optional[DFGGraph] = None) -> AngrFunctionResult:
        """分析函数，结合动态追踪数据识别未触发分支。"""
        cfg = self.build_cfg()
        func = cfg.kb.functions[func_addr]
        
        # 提取基本块
        blocks = []
        for block_addr in func.block_addrs:
            block = self.project.factory.block(block_addr)
            blocks.append({
                'addr': block_addr,
                'size': block.size,
                'insns': block.capstone.insns,
                'has_branch': block.vex.jumpkind != 'Ijk_Boring',
            })
        
        # 符号执行：探索未触发的分支
        uncovered_paths = []
        if dynamic_trace:
            dynamic_blocks = set(dynamic_trace.executed_blocks)
            static_blocks = set(func.block_addrs)
            uncovered = static_blocks - dynamic_blocks
            
            for block_addr in uncovered:
                result = self._symbolic_execute_to_block(func_addr, block_addr)
                if result and result.satisfiable:
                    uncovered_paths.append({
                        'target': block_addr,
                        'input_constraints': result.constraints,
                        'concrete_inputs': result.concrete_inputs,
                    })
        
        return AngrFunctionResult(
            cfg=func.transition_graph,
            blocks=blocks,
            uncovered_paths=uncovered_paths,
        )
        
    def _symbolic_execute_to_block(self, start_addr: int, target_addr: int,
                                   timeout: int = 30) -> Optional[SymbolicResult]:
        """符号执行：从 start_addr 到 target_addr，求解触发条件。"""
        state = self.project.factory.call_state(start_addr)
        simgr = self.project.factory.simulation_manager(state)
        simgr.explore(find=lambda s: s.addr == target_addr, timeout=timeout)
        
        if simgr.found:
            found_state = simgr.found[0]
            solver = found_state.solver
            concrete = {}
            for sym in solver.variables:
                val = solver.eval(sym)
                concrete[str(sym)] = val
            return SymbolicResult(
                satisfiable=True,
                constraints=found_state.solver.constraints,
                concrete_inputs=concrete,
            )
        return SymbolicResult(satisfiable=False)
```

**与其他开源工具的协作**：

| 工具 | 角色 | 与 Angr 的关系 |
|------|------|---------------|
| **Angr** | 符号执行 + 静态 CFG + 约束求解 | 核心引擎 |
| **Z3** (`z3-solver`) | 基本块级快速约束求解 | 独立于 Angr，用于快速验证 |
| **Unicorn** (`unicorn`) | CPU 模拟验证 | 验证 Angr 求解结果的安全性 |
| **Frida** (`frida-tools`) | 跨平台动态插桩 | 替代 Windows API 调试器，提供动态追踪数据给 Angr |
| **Capstone** (`capstone`) | 多架构反汇编 | Angr 内部已使用，作为 ARM64/MIPS 回退 |

---

## Layer 2: Ghidra 集成层（静态→动态衔接）

> **详细设计见第 4 节（致命缺口层详细设计）→ 4.1 Ghidra 集成层。**

**核心定位**：连接 Ghidra 的静态分析成果与 MemoryGraph 的动态分析运行时。不是"从头实现 IR"，而是"利用 Ghidra 的 P-Code 和反编译器，在动态追踪时实时注入语义"。

**关键组件**：
- **GhidraBridge**: 静态分析导入（内存镜像 → Headless 分析 → 结果导入知识库）
- **PCodeTranslator**: P-Code → 简化语义描述（供 LLM 理解，无需自研 IR）
- **DecompilerBridge**: 反编译代码 + 动态寄存器值注入（增强型 LLM 提示）

**设计原则**：
- 不重复造轮子：Ghidra 的反编译器和 P-Code 已经是工业级 IR
- 实时衔接：断点命中时毫秒级查询 Ghidra 知识库
- 动态增强：静态推断 + 动态值 = 带实时注释的伪 C 代码
- 结构体修正：动态访问未覆盖偏移时自动扩展 Ghidra 结构体

**示例（P-Code → 语义描述）**：

```
P-Code (Ghidra 输出):
  LOAD ram($U0:8) = *[ram]int32_t (RBX + 0x10:8)
  INT_ADD EAX = $U0 + 5:4
  INT_EQUAL $U1 = EAX == 100:4
  CBRANCH [0x1234:8], $U1
  STORE *[ram] (RBX + 0x10:8) = EAX

PCodeTranslator 输出 (LLM 可理解):
  "从 [RBX+0x10] 读取 int32_t，加 5，比较是否等于 100，
   如果等于则跳转到 0x1234，最后写回 [RBX+0x10]"

DecompilerBridge 输出 (带动态值):
  ```c
  // 函数: Player::UpdateHealth (Ghidra 识别)
  void __fastcall Player_UpdateHealth(Player *this, int delta)
  {
      // 动态值: this = 0x7FF6A00B1234 (Player*)
      // 动态值: delta = 5
      int current = this->health;  // 当前值: 95 (从 [RBX+0x10] 读取)
      current += delta;            // 95 + 5 = 100
      if (current == 100) {        // 条件成立！
          LevelUp(this);           // 调用等级提升函数
      }
      this->health = current;      // 写回 100
  }
  ```
```

**实现状态**：🔴 未完善。已有 `ghidra_scripts/ExportStructAccess.java` 和 `tracer_v2.py` 的 GhidraBridge 原型，但缺少：
- 内存镜像自动导出 + Headless 调用封装
- 分析结果实时查询（断点命中时）
- 结构体动态修正闭环
- P-Code 简化翻译层

---

---

## Layer 1: 底层引擎（含反混淆对抗）

### 8.1 mg_engine.dll (C++ 加速)

| 功能 | 状态 | 接口 |
|------|------|------|
| 内存扫描 | ✅ 完成 | `engine.first_scan()` / `engine.next_scan()` |
| 指针链扫描 | ✅ 完成 | `engine.pointer_chain_scan()` |
| 时序追踪 | ✅ 完成 | `engine.track_value()` |
| 数据分类 | ✅ 完成 | `engine.classify_values()` |
| 因果关联 | ✅ 完成 | `engine.correlation_graph()` |

### 8.2 Zydis (v4.1.1) 反汇编

```python
from disasm.zydis_engine import disassemble_at

instructions = disassemble_at(address="0x7FF6A0010000", count=20)
# 返回: [{"address": "0x...", "bytes": "48 89 5C 24 08", 
#         "mnemonic": "mov", "operands": ["rbx", "[rsp+0x8]"]}, ...]
```

---

## Layer 0: 系统接口

### 9.1 Windows API 封装

```python
core/winapi.py:
- OpenProcess(pid, access) → HANDLE
- ReadProcessMemory(hProcess, addr, size) → bytes
- WriteProcessMemory(hProcess, addr, data) → bool
- VirtualQueryEx(hProcess, addr) → MEMORY_BASIC_INFORMATION
- EnumProcessModulesEx(hProcess) → List[(base, size)]  # 64位安全
- GetModuleInformation(hProcess, hModule) → MODULEINFO
- CreateToolhelp32Snapshot(flags, pid) → HANDLE  # 进程/线程枚举
```

### 9.2 全局状态管理

```python
core/state.py:
g_hProcess: HANDLE       # 当前附加进程句柄
g_pid: int               # 当前进程 PID
g_dfg: Optional[DFGGraph] = None  # 运行时数据流图（进程切换时重置）
```

---

## 8. GUI 与 API 层

### 10.1 Flask 后端端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/attach` | POST | 附加进程 |
| `/api/launch` | POST | 启动并附加进程 |
| `/api/intent/start` | POST | 启动 IntentAgent |
| `/api/intent/status` | GET | 轮询 Agent 状态 |
| `/api/intent/response` | POST | 提交用户回复 |
| `/api/intent/stop` | POST | 停止 Agent |
| `/api/scan/first` | POST | 首次扫描 |
| `/api/scan/next` | POST | 下次扫描 |
| `/api/memory/read` | POST | 读取内存 |
| `/api/memory/write` | POST | 写入内存 |
| `/api/track/start` | POST | 启动追踪工作流 |
| `/api/track/stop` | POST | 停止追踪 |

### 10.2 前端状态映射

| 后端状态 | 前端显示 | 说明 |
|----------|----------|------|
| `idle` | 空闲 | Agent 未运行 |
| `analyzing_process` | 分析进程... | 初始化分析 |
| `waiting_user` | 等待用户 | 需要用户输入 |
| `thinking` | 处理中... | LLM 调用中（Act 模式） |
| `running_tool` | 执行工具... | 工具执行中 |
| `done` | 完成 | 会话结束 |
| `error` | 错误 | 发生错误 |

---

## 9. 树与图的衔接：完整工作流

### 11.1 WorkflowEngine（自动化工作流）

```
Phase 1: SELECTING (Top-Down)
  ├── ProcessAnalyzer 分析进程结构
  ├── 识别主模块、.text/.data 段、导出/导入表
  ├── 提取字符串资源（关键词定位）
  └── 输出扫描建议（"先扫 .data 段，再扫堆区域"）
       ↓
Phase 2: BREAKPOINTS_SET (Bottom-Up 起点)
  ├── 在候选地址设置断点（硬件/内存）
  ├── 启动数据收集器
  └── 进入监控状态
       ↓
Phase 3: COLLECTING (Bottom-Up 数据累积)
  ├── 收集断点命中数据（EIP、寄存器、调用栈）
  ├── 收集扫描结果变化
  └── 收集指针链追踪数据
       ↓
Phase 4: DFG_BUILT (Bottom-Up 图构建)
  ├── 将命中数据注入 DFGGraph
  ├── 构建指令 → 变量 → 调用帧的边
  ├── MemoryRelationshipGraph 推断结构体
  └── 生成数据流报告
       ↓
Phase 5: AI_ANALYZING (LLM 推理)
  ├── 构建结构化 prompt（DFG 摘要 + 代码片段）
  ├── LLM 分析函数语义、结构体布局
  └── 输出推断报告
       ↓
Phase 6: COMPLETED
  ├── 生成 Markdown 报告
  ├── 导出结构体定义（C/Python）
  └── 保存图谱 JSON
```

### 11.2 IntentAgent（交互式探索）

```
用户: "找到金币数量"
  → Agent: first_scan(type=3, value=unknown) → 42 个候选地址
  
用户: "我现在的金币是 100"
  → Agent: 修改自身价值，next_scan(filter=exact, value=100) → 3 个候选
  
用户: "在第一个地址设置断点"
  → Agent: set_breakpoint(addr=0x1234, size=4, mode=write) → 断点 ID
  
用户: "花掉一些金币"
  → Agent: get_breakpoint_hits(limit=10) → 命中记录
  → Agent: disassemble(addr=命中EIP, count=20) → 反汇编代码
  → Agent: 分析代码，发现 [rbx+0x10] 是金币字段，rbx 是 Player 结构体指针
  → Agent: 推断 Player 结构体布局
  
用户: "找到 Player 指针"
  → Agent: resolve_pointer(base=0x1234, offsets=[0x0, 0x8, 0x10]) → 最终地址
  → Agent: 发现指针链: Base → Module Static → Player* → Health/Gold
```

---

## 10. 已知问题与修复记录

### 12.1 已修复

| 问题 | 原因 | 修复 | 文件 |
|------|------|------|------|
| 64 位模块地址溢出 | `CreateToolhelp32Snapshot` 截断 64 位地址 | 改用 `EnumProcessModulesEx` | `core/winapi.py`, `core/process_analyzer.py` |
| LLM 编造反汇编结果 | 4B 模型无法遵循 `<思考>` 格式 | ReAct → Act 模式 | `core/intent_agent.py` |
| 上下文爆炸 400 错误 | 工具结果 JSON 直接塞进 history | 工具结果外部化 + 压缩 | `core/intent_agent.py` |
| 进程切换不刷新 | 旧分析结果不匹配新进程 | 轮询检测 PID 变化，自动刷新 | `core/intent_agent.py` |
| 交互模式下自动扫描被阻止 | 确认对话框被当作拒绝 | 改为 `WAITING_USER` 等待修复 | `core/intent_agent.py` |
| 重复显示思考内容 | `<回复>` 被错误解析为 thought | 修正 `_parse_llm_response` | `core/intent_agent.py` |

### 12.2 待解决

| 问题 | 优先级 | 方案 |
|------|--------|------|
| 会话数据丢失（无持久化） | **P0** | 实现 SQLite 四分层存储 |
| 9B 模型上下文需手动设 16K+ | P1 | 文档化 + 检测自动提示 |
| 内存断点实际功能未实现 | P1 | 完成硬件断点 + 调试器集成 |
| 调用栈重建未实现 | P1 | 完成栈回溯模块 |
| 控制流图（CFG）未实现 | P2 | 基于反汇编构建 CFG |
| 符号执行（简化版） | P3 | 路径分析引擎 |

---

## 11. 开发路线图

---

## 12. 文件索引

| 文件 | 行数 | 说明 |
|------|------|------|
| `core/intent_agent.py` | 1724 | IntentAgent (Act 模式) |
| `core/workflow_engine.py` | ~1200 | WorkflowEngine (自动化状态机) |
| `core/dfg.py` | ~400 | DFGGraph (数据流图) |
| `core/agents/memory/relationship_graph.py` | ~300 | MemoryRelationshipGraph (结构推断) |
| `core/process_analyzer.py` | ~500 | ProcessAnalyzer (静态分析) |
| `core/winapi.py` | ~600 | Windows API 封装 |
| `core/state.py` | ~200 | 全局状态管理 |
| `gui/server.py` | ~800 | Flask API 后端 |
| `gui/static/js/panels/intent.js` | ~433 | 前端 Intent 面板 |
| `memory/operations.py` | ~400 | 内存读写操作 |
| `memory/scanner.py` | ~500 | 内存扫描引擎 |
| `disasm/zydis_engine.py` | ~300 | Zydis 反汇编封装 |
| `mg_engine/` | - | C++ 引擎源码 |
| `docs/ARCHITECTURE.md` | 339 | 旧架构文档（V1） |
| `../project/design_v2_complete.md` | 1992 | V2 设计文档 |
| `../frontend-agent/CONTEXT_COMPRESSION_DESIGN.md` | 461 | 上下文压缩设计 |
| `ARCHITECTURE_v3.md` | - | 本文档（V3） |

---

## 13. 参考文献

| 来源 | 用途 |
|------|------|
| AgentBoard (NeurIPS 2024) | ReAct vs Act 模式在长交互中的性能对比 |
| MemGPT | 三层记忆架构（Core/Compressed/Recent） |
| Letta / LangChain Deep Agents | 工具结果外部化策略 |
| BITY / TYGR / STATEFORMER | MemoryRelationshipGraph 设计灵感 |
| Ghidra / IDA Pro | 逆向工程工作流参考 |

---

**文档结束。本文档描述 MemoryGraph 截至 2026-06-22 的完整架构状态，包括已完成的重构和待实现的存储层设计。**
