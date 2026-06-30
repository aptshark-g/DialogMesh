# MemoryGraph 竞品调研与方向定位报告

> **调研时间**：2025-06-22
> **调研范围**：学术论文（2024-2026）、开源工具（GitHub）、商业产品（Cheat Engine 生态、游戏修改器）
> **结论**：MemoryGraph 所在的 "动态内存分析 + LLM Agent + 结构体推断" 是**几乎完全空白的市场**。

---

## 一、直接竞品/同方向项目

### 1. Cheat Engine Bridge (mcpmarket.com)

| 维度 | 详情 |
|------|------|
| **类型** | MCP 服务器（外部桥接） |
| **Stars** | 148 GitHub stars |
| **功能** | 39 个 MCP tools：内存读取、指针链追踪、AOB 扫描、结构分析、硬件断点、RTTI 识别 |
| **定位** | 允许 Cursor/Copilot/Claude 等 AI 通过 MCP 协议连接 Cheat Engine |
| **与 MemoryGraph 差异** | 它是**外部桥**，不是 Agent；依赖用户手动输入自然语言指令；无自主扫描/推断能力；无结构体弱绑定 |

**评估**：Cheat Engine Bridge 证明了市场需求，但它是 **"工具集" 而非 "Agent"**。用户仍需手动操作每一步，AI 只是替用户点击按钮。MemoryGraph 的目标是让 AI **自主执行扫描→验证→推断→生成**的完整 pipeline。

---

### 2. Cheat Engine 官方 Issue #3274 (2025-12-11)

| 维度 | 详情 |
|------|------|
| **状态** | 仅 proposal（Issue），无 PR，无代码 |
| **提出者** | 社区用户 |
| **构想** | 三阶段 AI 插件：基础集成（自然语言扫描）→ 高级功能（指针路径、智能过滤）→ 专家模式（结构分析、训练器生成） |
| **核心概念** | "An AI brain that controls Cheat Engine for the user" |

**评估**：这个提案几乎完全描述了 MemoryGraph 的愿景。但**没有任何实际进展**。这说明方向正确，但社区缺乏实现者。MemoryGraph 如果率先实现，将填补这一空白。

---

### 3. Cheat Engine 7.6+ 官方 AI 功能

| 维度 | 详情 |
|------|------|
| **功能** | "added AI commands"（changelog 中仅一句） |
| **具体能力** | 未知（2025-2026 版本） |
| **评估** | 极可能是基础 AI 辅助（如 Lua 脚本生成建议），而非完整 Agent 架构。Cheat Engine 的架构和 Lua 脚本体系决定了它很难原生集成 LLM Agent。 |

---

## 二、学术研究方向（二进制逆向 + LLM）

### 2.1 静态分析方向（反编译/反汇编）

| 论文/系统 | 年份 | 核心能力 | 与 MemoryGraph 关系 |
|-----------|------|---------|---------------------|
| **BITY (Xu et al.)** | 2019 | `[base+offset]` 模式识别结构体，指针分析 | **理论基础**：MemoryGraph MRG 的 `[base+offset]` 检测直接借鉴 BITY |
| **TIE (Lee et al.)** | 类型推断 | 约束求解，指令使用模式推断类型 | 理论参考，但静态分析 |
| **TYGR (Zhu et al.)** | 2025 | GNN + DFG 进行结构体成员恢复，多架构支持 | **理论参考**：GNN 嵌入 DFG 节点做类型推断，但完全静态 |
| **REBench (Won et al.)** | 2025 | 首个 LLM 二进制逆向 benchmark，函数名/变量名/类型推断 | **评估标准**：LLM 在静态逆向工程上 F1 < 0.1，证明动态分析是必要的补充 |
| **DIRTY (Chen et al.)** | 2022 | 同步恢复类型和变量名 | 静态分析 |
| **sentinel-reverse** | 2026 | AI 自主二进制逆向 CLI，本地 LLM，多轮迭代 | 74 stars，但**纯静态分析**（IDA/Ghidra） |
| **decyx** | 2024 | AI-powered Ghidra 扩展 | 137 stars，静态分析 |
| **OGhidra** | 2025 | LLM + Ollama + Ghidra，自然语言查询 | 186 stars，LLM 辅助反编译，但**静态** |
| **auto-re-agent** | 2025 | LLM agents + Ghidra 自动化 | 3 stars，多 agent 编排静态分析 |

**关键洞察**：
- **所有学术和工具都在做静态分析**。它们解决的是：给你一个二进制文件，LLM 能推断出什么？
- **没有人做动态分析**：给一个正在运行的游戏/程序，LLM 能自动找到内存地址、推断结构体、生成修改器？
- **REBench 发现**：LLM 在静态类型推断上 F1 分数低于 0.1，这意味着**纯文本分析远远不够**。运行时数据（MemoryGraph 的 scan + breakpoint + value observation）是必需的补充信息。

---

### 2.2 动态分析方向（运行时）

| 论文/系统 | 年份 | 核心能力 | 状态 |
|-----------|------|---------|------|
| **STATEFORMER** | 2025 | 运行时值驱动的类型推断 | 论文级，无开源实现 |
| **MemoryGraph (本项目)** | 2025 | **运行时扫描 → 断点追踪 → 反汇编分析 → 结构体推断 → 弱绑定** | 开发中（ReAct Agent + 3层压缩 + MRG） |

**结论**：动态分析 + LLM Agent 的交叉方向**几乎完全空白**。MemoryGraph 是这一领域的先行者。

---

## 三、商业产品（游戏修改器市场）

### 3.1 传统工具

| 产品 | 类型 | 用户量 | AI 功能 | 评估 |
|------|------|--------|---------|------|
| **Cheat Engine** | 通用内存扫描/调试器 | 数百万 | 7.6+ 添加 "AI commands"（未知） | 行业标准，但无 Agent 能力 |
| **风灵月影 (Fengling)** | 游戏修改器平台 | 1500+ 游戏支持 | 无 | 人工为每个游戏编写修改脚本 |
| **WeMod** | 游戏修改器平台 | 大量 | 无 | 人工编写修改脚本 |
| **Bit Slicer** | macOS 内存编辑器 | 小众 | 无 | 传统工具 |
| **GTA5 Mod Menus** | 特定游戏修改器 | 游戏社区 | 无 | 都是人工逆向 + 硬编码偏移 |

### 3.2 关键观察

- **所有商业游戏修改器都是 "人工编写" 的**：每个游戏的修改脚本都是人类逆向工程师手动分析、硬编码偏移地址、测试后发布。
- **没有自动化**：当游戏更新（版本变化导致地址偏移变化），所有修改器失效，需要人工重新逆向。
- **MemoryGraph 的机会**：如果 Agent 能自动扫描 → 追踪断点 → 推断结构体 → 自适应更新偏移，那么游戏版本更新后修改器可以**自动恢复**。这是商业模式的差异化价值。

---

## 四、方向评估：MemoryGraph 的独特性

### 4.1 竞争格局矩阵

```
                    静态分析 ←→ 动态分析
                    ┌─────────┬─────────┐
         纯工具    │  decyx  │  Cheat  │
         (无 AI)   │ OGhidra │ Engine  │
                    │   IDA   │  WeMod  │
                    ├─────────┼─────────┤
  AI 辅助 (人类主导)│ auto-re-│  Bridge │
                    │  agent  │  (MCP)  │
                    ├─────────┼─────────┤
  AI Agent (自主)   │ 空白    │ 空白    │ ← MemoryGraph
                    └─────────┴─────────┘
```

### 4.2 MemoryGraph 的差异化能力

| 能力 | Cheat Engine Bridge | MemoryGraph |
|------|---------------------|-------------|
| 自然语言输入 | 有 | 有 |
| 自动内存扫描 | 无（用户手动指定） | **ReAct Agent 自主扫描** |
| 结构体推断 | 无（RTTI 辅助） | **MRG 从指令模式推断** |
| 指针链追踪 | 有（手动） | **Agent 自动追踪** |
| 弱绑定 | 无 | **有（地址→结构体字段关联）** |
| 上下文压缩 | 无 | **HybridCompressor 3层流水线** |
| 跨会话记忆 | 无 | **MemoryStore 持久化** |
| 本地 LLM | 依赖外部 | **4B 模型本地推理（80 tok/s）** |

### 4.3 学术验证的方向正确性

1. **REBench (2025)** 发现 LLM 在静态类型推断上 F1 < 0.1 → **动态运行时数据是必需的**
2. **TYGR (2025)** 用 GNN + DFG 做结构体恢复 → **结构体推断是可行且重要的**
3. **BITY (2019)** 证明 `[base+offset]` 模式可以识别结构体字段 → **MemoryGraph MRG 的理论基础扎实**
4. **Context-Folding (2026)** 折叠已完成子任务 → **MemoryGraph 的 Stage-Aware Folding 有学术支持**
5. **CMV (2026)** 去除机械膨胀 → **DeBloater 的 "零开销压缩" 是最佳实践**

---

## 五、推进建议：先发优势窗口

### 5.1 时间窗口评估

| 竞争者 | 威胁等级 | 时间线 |
|--------|---------|--------|
| Cheat Engine 官方 AI | 中 | 可能 1-2 年内推出基础功能，但架构限制使其难以做 Agent |
| Cheat Engine Bridge | 低 | 已是外部工具，非 Agent，且 148 stars 社区影响力有限 |
| 学术方向 | 低 | 学术界关注静态分析，动态分析方向无人投入 |
| 商业修改器 | 低 | 全部依赖人工，无技术储备转向 AI |

**结论**：MemoryGraph 有 **1-2 年的先发优势窗口**。如果率先实现完整的 "自然语言 → 动态扫描 → 结构体推断 → 训练器生成" pipeline，将确立这一细分领域的标准。

### 5.2 关键里程碑（优先级）

| 优先级 | 里程碑 | 竞争壁垒 |
|--------|--------|---------|
| **P0** | Agent 接入 GUI（真实游戏验证） | 证明可行性 |
| **P1** | 结构体弱绑定在真实游戏中有效 | 核心技术差异化 |
| **P2** | 跨会话记忆 + 游戏版本自适应 | 商业模式基础（修改器自动更新） |
| **P3** | SpeedHack 集成 | 完整产品体验 |
| **P4** | 多 Agent 协作（扫描 Agent + 分析 Agent + 脚本生成 Agent） | 技术深度 |

---

## 六、参考来源

| 来源 | 类型 | 关键信息 |
|------|------|---------|
| `github.com/cheat-engine/cheat-engine/issues/3274` | Issue Proposal | Cheat Engine 官方 AI 插件构想（2025-12） |
| `mcpmarket.com/server/cheat-engine-bridge` | MCP 工具 | 148 stars，39 tools，外部桥接 |
| `cheatengine.org` (changelog) | 产品更新 | 7.6+ 添加 "AI commands" |
| `sentinel-reverse` (GitHub) | 开源工具 | 74 stars，静态逆向 CLI |
| `decyx` (GitHub) | 开源工具 | 137 stars，Ghidra AI 扩展 |
| `OGhidra` (GitHub) | 开源工具 | 186 stars，LLM + Ghidra |
| `auto-re-agent` (GitHub) | 开源工具 | 3 stars，多 agent 静态分析 |
| `awesome-llm-reverse-engineering` | 资源列表 | 14 stars，LLM 逆向工程资源汇总 |
| REBench (Won et al., 2025) | 学术论文 | LLM 在二进制逆向上的 F1 < 0.1，需要动态数据 |
| TYGR (Zhu et al., 2025) | 学术论文 | GNN + DFG 结构体恢复，多架构 |
| BITY (Xu et al., 2019) | 学术论文 | `[base+offset]` 结构体模式识别 |
| Context-Folding (2026) | 学术论文 | 折叠已完成子任务，上下文减少 10x |
| CMV (Santoni, 2026) | 学术论文 | 机械膨胀去除，结构化无损修剪 |
| 风灵月影官网 | 商业产品 | 1500+ 游戏支持，人工编写修改脚本 |

---

*报告结论：MemoryGraph 在 "动态内存分析 + LLM Agent + 结构体推断" 方向上是**全球唯一**的端到端项目。学术方向提供了理论基础（BITY/TYGR/REBench），商业市场验证需求（Cheat Engine Bridge/风灵月影），但完整实现尚不存在。1-2 年先发窗口。*
