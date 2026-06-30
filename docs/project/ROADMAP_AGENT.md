# MemoryGraph Agent 转型路线图

> **目标**：将 MemoryGraph 从"手动内存分析工具"升级为"自主逆向工程 Agent"——能够自主发现、分析、验证和操作目标进程内存的 AI 系统。

---

## 一、当前状态诊断

### 1.1 已知局限分析

| 局限 | 根因 | 对Agent的影响 | 解决难度 |
|------|------|-------------|---------|
| 自动化工作流未闭环 | 一键逆向只生成提示词，不自动调用LLM | Agent无法自主决策 | 🔴 高 |
| Ghidra静态分析归档 | 接入成本高、维护重、与动态分析耦合弱 | Agent缺少静态分析工具 | 🟡 中 |
| 未经过真实游戏验证 | 只在测试靶机验证 | Agent训练环境不真实 | 🟡 中 |
| 无SpeedHack/脚本系统 | 未实现 | Agent缺少"执行能力" | 🟡 中 |

### 1.2 当前架构 → Agent架构映射

```
当前 MemoryGraph（手动工具）
    用户点击扫描 → 内存扫描 → 用户选择地址 → 用户设置断点 → 用户分析结果

目标 MemoryGraph Agent（自主系统）
    Agent 观察进程 → 自主扫描 → 自主推断地址含义 → 自主验证（断点+追踪）
    → 自主决策（修改/锁定/SpeedHack） → 自主学习 → 记录发现
```

---

## 二、Agent 核心架构设计

### 2.1 认知架构：ReAct + 工具调用

采用 **ReAct（Reasoning + Acting）** 循环，每次迭代包含：

```
┌─────────────────────────────────────────────────────┐
│  感知（Perception）                                    │
│  ─────────────────                                   │
│  • 内存扫描结果（地址、值、类型）                      │
│  • 断点命中记录（RIP、寄存器、内存值）                 │
│  • 反汇编上下文（指令、调用栈）                        │
│  • 时序变化（值变化模式、时间戳）                      │
│  • 进程状态（模块加载、线程活动）                      │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│  推理（Reasoning）—— LLM 作为大脑                      │
│  ─────────────────                                   │
│  • 分析当前内存状态，推断数据结构                       │
│  • 评估假设（"这个地址可能是HP，因为值在受伤时下降"）     │
│  • 选择下一步行动（扫描/断点/追踪/修改）                │
│  • 生成自然语言报告                                   │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│  行动（Action）—— 工具调用                             │
│  ─────────────────                                   │
│  • 扫描：first_scan / next_scan / pointer_scan        │
│  • 监控：set_breakpoint / start_trace / add_watch     │
│  • 修改：write_memory / set_speedhack / lock_value   │
│  • 分析：disassemble / build_dfg / analyze_pattern   │
│  • 报告：save_struct / generate_c_header            │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
        ┌──────────────┐
        │   记忆存储    │
        │  （Memory）   │
        └──────────────┘
```

### 2.2 工具层（Tools）

Agent 可调用的工具集合，对应现有模块的封装：

| 工具名 | 对应模块 | 功能 | 输出 |
|--------|---------|------|------|
| `scan_memory` | `memory/scanner.py` | 内存扫描（值/范围/未知） | 地址列表 + 当前值 |
| `read_memory` | `memory/operations.py` | 读取指定地址 | 字节数据 |
| `write_memory` | `memory/operations.py` | 修改指定地址 | 成功/失败 |
| `set_watchpoint` | `core/debugger.py` | 设置读写断点 | 断点ID |
| `get_hits` | `core/debugger.py` | 获取断点命中 | 命中记录列表 |
| `disassemble` | `analysis.zydis_engine` | 反汇编地址 | 指令列表 |
| `trace_execution` | `disasm.tracer_v2` | 指令追踪 | 追踪日志 |
| `build_dfg` | `core/dfg.py` | 构建数据流图 | DFG图数据 |
| `set_speedhack` | [新增] | 修改时间倍率 | 成功/失败 |
| `execute_script` | [新增] | 执行Lua/JS脚本 | 执行结果 |
| `attach_process` | `core/winapi.py` | 附加进程 | 进程句柄 |
| `enum_modules` | `memory/operations.py` | 枚举模块 | 模块列表 |
| `save_discovery` | [新增] | 保存发现到知识库 | 记录ID |
| `query_knowledge` | [新增] | 查询历史发现 | 相关记录 |

### 2.3 记忆层（Memory）

Agent 需要长期记忆来累积逆向工程知识：

```python
# 发现记录（Discovery）
{
    "id": "uuid",
    "timestamp": "2025-06-21T14:30:00",
    "type": "struct_field",  # struct_field / function / variable / pattern
    "process": "eldenring.exe",
    "module": "eldenring.exe+0x1A2B3C00",
    "address": 0x7FF123456789,
    "name": "player_hp",
    "inferred_type": "float32",
    "confidence": 0.85,
    "evidence": [
        {"type": "breakpoint_hit", "rip": 0x140001234, "value_change": "100.0 → 80.0"},
        {"type": "value_pattern", "pattern": "decreases_on_damage"},
    ],
    "related": ["player_max_hp", "player_mp"],
    "c_header": "float player_hp; // offset 0x10 from base",
}
```

存储后端：
- **短期记忆**：`state.py` 全局变量（当前会话）
- **中期记忆**：JSON文件 `.kimi/discoveries/`（跨会话）
- **长期记忆**：向量数据库（语义检索相似结构）→ [Phase 3]

### 2.4 多Agent协作（Multi-Agent）

将复杂任务分解为多个专业Agent：

```
┌────────────────────────────────────────┐
│           Orchestrator Agent           │
│         （任务分配 + 结果整合）           │
└──────────┬────────────┬───────────────┘
           │            │
    ┌──────▼──────┐ ┌───▼──────┐ ┌──────▼──────┐
    │ Scanner     │ │ Analyzer │ │ Exploiter   │
    │ Agent       │ │ Agent    │ │ Agent       │
    │ ──────────  │ │ ──────── │ │ ──────────  │
    │ 内存扫描     │ │ 结构推断  │ │ 修改/锁定   │
    │ 指针追踪     │ │ 函数识别  │ │ SpeedHack   │
    │ 值变化监控   │ │ 类型推断  │ │ 脚本执行    │
    └─────────────┘ └──────────┘ └─────────────┘
           │            │            │
           └────────────┴────────────┘
                        │
                 ┌──────▼──────┐
                 │ Reporter   │
                 │ Agent      │
                 │ ────────── │
                 │ 生成报告   │
                 │ C头文件    │
                 │ 使用文档   │
                 └────────────┘
```

---

## 三、四大局限 → 完成计划

### 3.1 局限一：自动化工作流闭环

**目标**：Agent 能自主完成"观察 → 分析 → 决策 → 行动 → 学习"循环

**当前状态**：
- `core/workflow_engine.py` 有状态机（IDLE → CONFIGURED → ... → COMPLETED）
- 但 `_step_ai_analysis` 只生成提示词，不自动调用 LLM
- `core/agents/` 有 ProviderManager（支持 Kimi/OpenAI/Claude/Ollama），但 CLI 模式下才使用

**实施计划**：

| 阶段 | 任务 | 文件/模块 | 关键实现 |
|------|------|----------|---------|
| **Phase 1** | 激活 ProviderManager | `core/agents/provider_manager.py` | 让 GUI 也能调用 LLM API（非CLI模式） |
| **Phase 1** | 设计 Agent 提示词模板 | `core/agents/prompts/` | 创建 system prompt：角色定义、工具描述、输出格式 |
| **Phase 1** | 工具调用协议 | `core/agents/tool_executor.py` | 定义JSON工具调用格式（类似OpenAI function calling） |
| **Phase 2** | 实现 ReAct 循环 | `core/agents/react_engine.py` | 观察 → LLM推理 → 解析工具调用 → 执行 → 反馈 → 循环 |
| **Phase 2** | 记忆系统集成 | `core/memory/` [新增] | 每次迭代保存发现，下次迭代可查询 |
| **Phase 3** | 多Agent编排 | `core/agents/orchestrator.py` | 分解任务、分配Agent、整合结果 |
| **Phase 3** | 自主模式UI | `gui/templates/index.html` | 添加"Auto Agent"标签页，展示Agent思考过程 |

**关键设计决策**：
- **LLM调用模式**：不是每次断点命中都调用LLM（太贵、太慢），而是：
  - 收集一批命中（如10-20条）→ 批量送入LLM → 得到分析 → 决定下一步
  - 设置"思考间隔"（如每5秒或每N次命中）
- **成本控制**：提供本地模型选项（Ollama），默认先用本地模型，复杂任务再调用云端
- **安全边界**：Agent不能随意修改内存 → 需要"确认级别"（完全自主 / 高价值确认 / 完全手动）

---

### 3.2 局限二：Ghidra 静态分析

**目标**：Ghidra 作为 Agent 的"静态分析工具"，按需调用，不常驻

**当前状态**：
- `recycle/analysis/` 中有完整 Ghidra 分析链（`ghidra_engine.py`, `ghidra_bridge.py`, `struct_inference_v2.py`）
- 之前 OSGi 缓存问题导致编译不稳定，但已有解决方案

**实施计划**：

| 阶段 | 任务 | 策略 | 关键实现 |
|------|------|------|---------|
| **Phase 1** | 恢复 Ghidra 基础功能 | 从 `recycle/` 恢复 `analysis/ghidra_engine.py` | 提供 `analyze_binary()` 函数：输入exe路径 → 输出函数列表+结构体候选 |
| **Phase 1** | 封装为 Agent 工具 | 新增 `tools/ghidra_analyzer.py` | 提供 `ghidra_analyze(exe_path)` 函数，封装所有 Ghidra 调用细节 |
| **Phase 2** | 动态-静态交叉验证 | `analysis/cross_validator.py` | Agent 将 Zydis 发现的指令地址与 Ghidra 函数列表交叉验证，确认函数边界 |
| **Phase 2** | 按需触发策略 | `core/agents/` 决策逻辑 | Agent 只在"需要确认函数边界"或"需要识别结构体布局"时调用 Ghidra，而非每次扫描都调用 |
| **Phase 3** | Ghidra 结果缓存 | `.kimi/ghidra_cache/` | 缓存分析结果，同一二进制只分析一次 |

**关键设计决策**：
- Ghidra 不是必需的，而是 Agent 的"可选工具"——如果 Ghidra 不可用，Agent 用纯动态分析也能工作
- 将 Ghidra 封装为独立服务（子进程 / REST API），避免 Python 直接操作 Ghidra 的复杂性
- 用之前验证通过的 `ExportStructAccess.java` 方案（OSGi 缓存清理 + `FunctionIterator` + `CodeUnit`）

---

### 3.3 局限三：真实游戏/进程验证

**目标**：在真实环境中验证 Agent 的可靠性，并建立"训练数据集"

**实施计划**：

| 阶段 | 任务 | 验证目标 | 方法 |
|------|------|---------|------|
| **Phase 1** | 真实靶机验证 | 确认断点/追踪器在真实进程上稳定 | 用 `recycle/tools/target_game.py` 恢复的靶机，测试完整Agent循环 |
| **Phase 1** | 小型开源游戏 | 验证扫描+修改功能 | 选择 1-2 个开源游戏（如 [OpenRA](https://github.com/OpenRA/OpenRA)、[0 A.D.](https://github.com/0ad/0ad)），源码已知，可以验证Agent推断是否正确 |
| **Phase 2** | 商业游戏验证（低风险） | 验证断点追踪+结构推断 | 选择单机游戏（如 Elden Ring、Dark Souls Remastered、Hollow Knight），无反作弊，可放心调试 |
| **Phase 2** | 建立验证基准 | 可重复测试 | 记录"已知地址"（如HP、坐标、金币），看Agent能否自主发现 |
| **Phase 3** | 有保护的游戏 | 测试反反作弊应对 | 选择带Easy Anti-Cheat的游戏（如Apex Legends），但只在离线模式/训练场测试 |

**测试基准（Benchmark）**：

```python
# 已知答案的测试用例
BENCHMARK_CASES = [
    {
        "name": "player_hp_float",
        "game": "Hollow Knight",
        "type": "float",
        "expected_pattern": "decreases_on_damage",
        "hint": "health",
        "timeout_seconds": 60,
    },
    {
        "name": "player_position_vector3",
        "game": "Hollow Knight",
        "type": "struct",  # 3 floats (x, y, z)
        "expected_pattern": "changes_on_movement",
        "hint": "position",
        "timeout_seconds": 120,
    },
    {
        "name": "gold_int",
        "game": "Hollow Knight",
        "type": "int32",
        "expected_pattern": "increases_on_pickup",
        "hint": "geo",
        "timeout_seconds": 60,
    },
]
```

---

### 3.4 局限四：SpeedHack / 脚本系统

**目标**：给 Agent 提供"执行能力"——修改游戏逻辑、加速时间、自动化操作

**实施计划**：

| 阶段 | 功能 | 技术方案 | 难度 |
|------|------|---------|------|
| **Phase 1** | SpeedHack（时间倍率） | Hook `QueryPerformanceCounter` / `GetTickCount` / `timeGetTime` | 🟡 中 |
| **Phase 1** | 内存锁定（Lock） | 已有 `memory.watchlist` + `start_lock`，增强为"条件锁定"（如HP<50时锁定为100） | 🟢 低 |
| **Phase 2** | 脚本引擎（Lua） | 集成 LuaJIT / lupa，Agent 生成 Lua 脚本 → 用户确认 → 执行 | 🟡 中 |
| **Phase 2** | 脚本引擎（JavaScript） | 集成 QuickJS / 类似 CE 的 Auto Assembler | 🟡 中 |
| **Phase 3** | 代码注入（DLL Injection） | Agent 生成 DLL 注入代码，实现更复杂的功能（如渲染Hook、网络包拦截） | 🔴 高 |
| **Phase 3** | 内核调试（Kernel） | 考虑使用 [KernelFuzzer](https://github.com/) 或类似方案，绕过用户态保护 | 🔴 高（长期） |

**SpeedHack 技术方案**：

```cpp
// mg_engine.dll 新增 API：MG_SetSpeedHack
// Hook QueryPerformanceCounter
static LARGE_INTEGER g_qpc_base;
static double g_speed = 1.0;

BOOL WINAPI Hook_QueryPerformanceCounter(LARGE_INTEGER* lpPerformanceCount) {
    BOOL ret = Original_QueryPerformanceCounter(lpPerformanceCount);
    if (ret) {
        lpPerformanceCount->QuadPart = g_qpc_base.QuadPart + 
            (long long)((lpPerformanceCount->QuadPart - g_qpc_base.QuadPart) * g_speed);
    }
    return ret;
}
```

**Agent 使用场景**：
- "Agent 发现HP地址后，自动设置 SpeedHack×0.5，让玩家更容易测试受伤时的值变化"
- "Agent 发现时间变量后，设置 SpeedHack×10，加速验证时间相关逻辑"

---

## 四、完整 Roadmap

### Phase 1：Agent 基础设施（4-6 周）

**目标**：Agent 能完成一个最简单的自主任务——"找到一个已知的值"

| 周 | 任务 | 产出 |
|----|------|------|
| 1-2 | 恢复 Ghidra 基础功能，封装为工具 | `tools/ghidra_analyzer.py` 可调用 |
| 1-2 | 激活 ProviderManager，支持 GUI 调用 LLM | `gui/server.py` 新增 `/api/agent/llm` 路由 |
| 2-3 | 设计 Agent Prompt + 工具调用协议 | `core/agents/prompts/system.md` + `tool_schema.json` |
| 3-4 | 实现 ReAct 循环核心 | `core/agents/react_engine.py` + 单元测试 |
| 4-5 | 集成记忆系统（短期+中期） | `core/memory/` + JSON 存储 |
| 5-6 | GUI 添加 Auto Agent 标签页 | 展示 Agent 思考过程、工具调用、发现结果 |
| 5-6 | 真实靶机验证 | 跑通"找HP"完整Agent循环 |

**里程碑**：
```
用户选择进程 → 点击"Auto Agent" → Agent 自主扫描 → 发现地址 → 
设置断点验证 → 推断类型 → 生成报告 → 用户查看结果
```

### Phase 2：工具增强 + 多Agent（4-6 周）

**目标**：Agent 能处理复杂任务，多个专业Agent协作

| 周 | 任务 | 产出 |
|----|------|------|
| 1-2 | 实现 SpeedHack（mg_engine.dll） | `MG_SetSpeedHack()` API + GUI控制 |
| 1-2 | 实现脚本引擎（Lua）基础 | `script_engine/` 模块，可加载/执行 Lua |
| 2-3 | 多Agent编排器 | `core/agents/orchestrator.py` 实现任务分解 |
| 2-3 | Scanner Agent + Analyzer Agent | 两个专业Agent，各自有独立的提示词和工具集 |
| 3-4 | 动态-静态交叉验证 | Ghidra 函数列表与 Zydis 断点命中交叉验证 |
| 4-5 | 真实游戏验证（Hollow Knight / Dark Souls） | 建立 Benchmark，记录成功率 |
| 5-6 | 知识库增强（长期记忆） | 向量数据库（ChromaDB / 轻量级方案）存储发现 |

**里程碑**：
```
Agent 自主完成：
1. 发现 player_hp (float)
2. 发现 player_position (Vector3 struct)
3. 发现 inventory array (pointer chain)
4. 生成 C 头文件 + 使用文档
5. 用户评分：Agent 推断正确率 > 70%
```

### Phase 3：高级能力 + 生产化（6-8 周）

**目标**：Agent 能处理复杂保护、生成高质量报告、接近可用工具

| 周 | 任务 | 产出 |
|----|------|------|
| 1-2 | 指针链自动解析（多级） | Agent 能自动追踪 pointer chain 到基址 |
| 1-2 | 反反作弊基础（绕过EasyAntiCheat） | 内核驱动或合法绕过方案（仅学习/测试） |
| 2-3 | 代码注入（DLL Injection） | Agent 生成/注入 DLL，实现复杂功能 |
| 2-4 | 报告系统升级 | 自动生成 Markdown 报告 + C 头文件 + Python 读取脚本 |
| 4-5 | 社区/分享功能 | 分享发现的结构（类似 Cheat Engine Tables） |
| 5-6 | 性能优化 | C++ 引擎优化扫描速度、减少 Python 调用开销 |
| 6-8 | 文档 + 教程 | 完整文档、视频教程、Benchmark 结果 |

**里程碑**：
```
- 在 3 款不同游戏中验证成功
- 平均发现时间 < 5 分钟（简单值）/ < 30 分钟（结构体）
- 正确率 > 80%
- 可以发布 v1.0 Beta
```

---

## 五、技术决策要点

### 5.1 LLM 选择策略

| 场景 | 推荐模型 | 原因 |
|------|---------|------|
| 快速推理（工具选择） | 本地 Qwen2.5-7B / Llama-3.1-8B | 快、免费、保护隐私 |
| 复杂分析（结构推断） | Kimi k1.5 / GPT-4o / Claude 3.5 | 强推理、长上下文 |
| 代码生成（C头文件） | Claude 3.5 Sonnet / GPT-4o | 代码能力强 |
| 预算有限 | Ollama 本地运行 | 零成本 |

**架构**：ProviderManager 已支持多模型切换，Agent 根据任务复杂度自动选择（或用户配置）

### 5.2 记忆存储方案

| 阶段 | 方案 | 理由 |
|------|------|------|
| Phase 1-2 | JSON文件 + 简单索引 | 简单、可版本控制、无额外依赖 |
| Phase 3+ | ChromaDB / SQLite + 向量索引 | 支持语义检索（"找类似HP的结构"） |

### 5.3 安全与伦理

- **反作弊**：明确只在离线模式/单机游戏/测试靶机上使用，不用于在线竞技游戏
- **代码注入**：用户必须显式确认，Agent 不能自动注入代码到未知进程
- **数据隐私**：LLM 调用时不上传完整内存dump，只上传结构化数据（地址、值、模式）
- **开源协议**：考虑 AGPL / GPL 确保衍生作品开源，防止被滥用

---

## 六、与 GitHub 发布的衔接

### 当前发布策略

**建议：Phase 1 完成后发布 v0.2**
- 包含：Agent 基础循环 + ReAct + GUI Auto Agent 标签页 + 靶机验证
- 不包含：SpeedHack、Ghidra、多Agent编排（留到 v0.3）
- README 明确标注："Working Prototype with Agent Capabilities"

### 版本规划

| 版本 | 内容 | 状态 |
|------|------|------|
| v0.1 | 当前状态：工具原型 + 回收站 | ✅ 已达成 |
| **v0.2** | **Agent 基础：ReAct + LLM + 记忆 + 靶机验证** | 🎯 目标 |
| v0.3 | SpeedHack + 脚本 + 多Agent + Ghidra | 待规划 |
| v0.4 | 真实游戏验证 + 知识库 + 报告系统 | 待规划 |
| v1.0 | 生产可用：稳定、文档完善、社区贡献 | 长期目标 |

---

## 七、下一步行动

**立即可启动（本周）**：
1. ✅ 恢复 `target_game.py` 到 `tools/` 作为 Agent 测试靶机
2. ✅ 设计 `core/agents/prompts/system.md` —— Agent 角色定义和工具描述
3. ✅ 实现 `core/agents/react_engine.py` —— 最小可用 ReAct 循环（硬编码一个"找HP"任务）

**需要确认的问题**：
1. LLM 调用预算：是否有 Kimi API Key / OpenAI API Key？还是用纯本地 Ollama？
2. 目标游戏：选择哪款游戏作为第一个真实验证目标？（建议 Hollow Knight——无反作弊、结构简单、社区熟悉）
3. 团队资源：你一个人推进，还是计划开源后吸引贡献者？

---

*规划时间：2025-06-21*
*版本：v1.0-draft*
*目标：从 MemoryGraph Tool → MemoryGraph Agent*
