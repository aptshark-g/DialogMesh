# MemoryGraph Kimi Code CLI Integration Guide

> This guide explains how to use MemoryGraph with Kimi Code CLI (Kimi K2.7 Code)
> AI capabilities through the terminal interface. No API Key required - uses your
> Kimi membership directly via the CLI tool.

---

## 1. Install Kimi Code CLI

### Windows (PowerShell)

```powershell
irm https://code.kimi.com/kimi-code/install.ps1 | iex
```

### macOS / Linux

```bash
curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash
```

### Verify Installation

```bash
kimi --version
```

---

## 2. Login (OAuth Auto-Auth)

```bash
kimi login
```

This opens a browser for OAuth authentication. No manual API Key management needed.

---

## 3. Project Setup

Navigate to the MemoryGraph project directory:

```bash
cd C:\Users\APTShark\PycharmProjects\MemoryGraph
```

Kimi CLI will automatically read the project structure and context.

---

## 4. Common Workflows

### Workflow A: AI-Powered Code Analysis

**Step 1**: Generate analysis prompt via CLI tool

```bash
python cli.py analyze mg_engine/src/breakpoint.cpp --context "Phase 4 debugger with hardware breakpoints"
```

**Step 2**: Copy the generated prompt (from JSON output)

**Step 3**: Paste into Kimi CLI terminal:

```
> [paste the prompt here]
```

Kimi AI will analyze the code, find bugs, and suggest fixes.

### Workflow B: Interactive Debugging with AI

**In Kimi CLI terminal**:

```
> 请分析 breakpoint.cpp 中的 _capture_hit_context 函数，是否存在缓冲区溢出风险？
```

Kimi CLI will read the file, analyze it, and give you a detailed report.

### Workflow C: Automatic Fix Application

**Step 1**: Ask Kimi to fix a bug:

```
> 请修复 breakpoint.cpp 第 220 行的缓冲区溢出问题：val_buf[8] 但读取 bp_size=4096
```

**Step 2**: Kimi CLI will suggest code changes. Review the diff.

**Step 3**: Apply the fix (Kimi CLI can edit files directly).

### Workflow D: Build & Test Cycle

```bash
# Build the DLL
python cli.py build

# Or in Kimi CLI:
> 请编译 MemoryGraph 的 C++ DLL 并检查是否有编译错误
```

### Workflow E: Reverse Engineering with DFG

```bash
# Start the server
python cli.py server

# In browser: attach to process, set breakpoints, build DFG

# Then in Kimi CLI:
> 请根据 DFG 报告分析这个程序的数据结构。这是我的断点命中记录...
```

---

## 5. CLI Commands Reference

| Command | Description | Example |
|---------|-------------|---------|
| `attach <pid>` | Attach to process | `python cli.py attach 1234` |
| `scan --value <v>` | First memory scan | `python cli.py scan --value 100` |
| `next --value <v>` | Next scan | `python cli.py next --value 50` |
| `build` | Build C++ DLL | `python cli.py build` |
| `analyze <file>` | Generate AI analysis prompt | `python cli.py analyze src.cpp` |
| `explain <file>` | Generate AI explanation prompt | `python cli.py explain src.cpp` |
| `fix <file> --error <e>` | Generate AI fix prompt | `python cli.py fix src.cpp --error "buffer overflow"` |
| `server` | Start Flask GUI | `python cli.py server --port 8080` |

---

## 6. GUI + CLI Hybrid Workflow

**Best practice**: Use both interfaces together:

```
┌─────────────────────────────────────────┐
│  Kimi Code CLI (Terminal)               │
│  - AI analysis, code review, bug fixes    │
│  - Natural language commands            │
└────────────────────┬────────────────────┘
                     │
                     │ (copy/paste prompts)
                     │
┌────────────────────▼────────────────────┐
│  MemoryGraph GUI (Browser)                │
│  - Memory scanning, debugging, DFG      │
│  - Visual data flow graphs              │
└─────────────────────────────────────────┘
```

**Example session**:

1. Start GUI: `python cli.py server`
2. Open browser, attach to target process, run scans
3. In Kimi CLI: `> 请分析我的扫描结果，找出可能的变量类型`
4. Kimi CLI reads scan results, suggests analysis approach
5. Back in GUI: set breakpoints, build DFG
6. In Kimi CLI: `> 根据 DFG 数据推断目标程序的数据结构`
7. Kimi AI generates reverse engineering report

---

## 7. Prompt Templates for Kimi CLI

### Template 1: Security Audit

```
请对 MemoryGraph 项目的以下文件进行安全审计：
- mg_engine/src/breakpoint.cpp
- mg_engine/src/scanner.cpp
- mg_engine/src/pointer.cpp

重点关注：
1. 缓冲区溢出
2. 竞争条件
3. 内存泄漏
4. 整数溢出

给出每个问题的具体位置、严重程度、修复建议。
```

### Template 2: Performance Optimization

```
请分析 MemoryGraph 的扫描引擎性能瓶颈：
- scanner.cpp 和 scanner_opt.cpp
- 当前使用 memchr + AVX2 对齐比较
- 处理大型进程（64GB+）时可能有性能问题

给出优化建议，包括：
1. 算法改进
2. 并行化策略
3. 内存使用优化
```

### Template 3: Reverse Engineering from DFG

```
我使用 MemoryGraph 对某个程序进行了动态分析：
- 扫描到 3 个可疑变量地址
- 设置了写断点，捕获了 15 次命中
- 调用栈显示写入指令来自 Game.exe+0x123456
- DFG 图显示变量 A 和变量 B 有强相关性

请帮我：
1. 推断这些变量可能代表什么游戏数据
2. 分析写入逻辑的功能
3. 给出反编译伪代码
4. 建议下一步的逆向分析方向
```

---

## 8. Troubleshooting

### Issue: Kimi CLI cannot read project files

**Solution**: Ensure Kimi CLI is launched from the project directory:

```bash
cd C:\Users\APTShark\PycharmProjects\MemoryGraph
kimi
```

### Issue: `python cli.py` not found

**Solution**: Use full Python path or add to PATH:

```bash
C:\Python312\python.exe cli.py analyze src.cpp
```

### Issue: Kimi CLI says "Access Denied" for memory operations

**Solution**: MemoryGraph requires admin privileges for process attachment. Run Kimi CLI as Administrator:

```powershell
# Right-click PowerShell -> Run as Administrator
kimi
```

### Issue: DLL build fails in Kimi CLI

**Solution**: Ensure Visual Studio Build Tools are installed and MSBuild is in PATH:

```bash
# Verify MSBuild exists
where msbuild
# If not found, add to PATH:
$env:PATH += ";C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\MSBuild\Current\Bin"
```

---

## 9. Architecture Notes

```
Kimi Code CLI (Node.js)
    ├── AI Engine (Kimi K2.7 Code)
    ├── File System Access
    ├── Command Execution
    └── MCP Protocol Support (future)

    \
     \
      \
       MemoryGraph Project
        ├── cli.py           (CLI entry point)
        ├── gui/server.py    (Flask backend)
        ├── mg_engine/       (C++ DLL)
        └── core/            (Python core modules)
```

**Key point**: Kimi CLI does NOT call MemoryGraph's API. Instead, it operates as a **development environment** - reading files, executing commands, and using its own AI engine to analyze the project.

---

## 10. Next Steps

1. **Install Kimi CLI**: Follow Section 1 above
2. **Login**: `kimi login`
3. **Try a workflow**: Pick Workflow A, B, or C from Section 4
4. **Explore hybrid mode**: Run both GUI and CLI simultaneously

For questions or issues, check the Kimi Code documentation:
https://www.kimi.com/code/docs/
