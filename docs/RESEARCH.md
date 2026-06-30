# 逆向工具开源生态调研报告

> 调研目标：寻找与 MemoryGraph 定位（自动化逆向推理引擎）最接近的开源项目，识别可复用组件，优化架构设计。

---

## 1. ReClass.NET — 最接近的现有实现（MIT 开源）

**项目**：https://github.com/ReClassNET/ReClass.NET

### 核心定位
专门用于**运行时内存结构重建**（Runtime Structure Reconstruction）。与 MemoryGraph 目标高度一致。

### 已有功能对比

| 功能 | ReClass.NET | MemoryGraph (当前) | 差距分析 |
|------|-------------|-------------------|----------|
| 内存节点类型 | ✅ 极其丰富（Hex/Int/Float/Vector/Matrix/Text/Pointer/VTable/Function） | ❌ 无节点系统 | ReClass 有完整的节点抽象，我们完全没有 |
| 内存扫描器 | ✅ 支持，可导入 CE/CrySearch 格式 | ✅ 自有 C++ 引擎 | 我们的扫描引擎是 C++ 化的，性能可能更好，但 ReClass 有成熟 UI |
| 调试器（断点） | ✅ "Find out what writes/accesses this address" | ❌ 只有 stub | **ReClass 已实现完整的 write/access 断点** |
| 代码生成器 | ✅ C++ / C# 自动生成 | ❌ 无 | 这是我们需要在 Phase 9 实现的 |
| 自动节点解剖 | ✅ Automatic Node Dissection | ❌ 无 | ReClass 能自动推断相邻字段类型 |
| 结构体可视化 | ✅ 实时内存视图 + 类型标注 | ❌ 只有 Hex 查看器 | ReClass 的 UI 是专业级 |
| 指针预览 | ✅ Pointer Preview | ✅ 指针扫描 | 我们的指针扫描是 C++ 化的，ReClass 是 UI 化的 |
| 插件系统 | ✅ 多语言插件（C++/C++/CLI/C#） | ❌ 无 | 可扩展性强 |
| 符号支持 | ✅ PDB 调试符号 / RTTI | ❌ 无 | 如果有符号，逆向难度大幅下降 |
| MCP/AI 集成 | ✅ ReClass.NET-MCP（JSON-RPC over TCP） | ❌ 无 | 2025 年已有 AI 集成 |

### 关键发现：ReClass.NET 的"自动节点解剖"

ReClass.NET 的 **Automatic Node Dissection** 正是我们 Phase 9 要实现的结构体推断：
- 读取内存后，根据值特征自动推断类型（如 `0x3F800000` → `float 1.0`，`0x00000000` → `null ptr`）
- 高亮变化内存（highlight changed memory）→ 判断活跃字段
- 指针预览（Pointer Preview）→ 自动追踪指针指向

**结论**：ReClass.NET 已经做了我们要做的大部分工作，但它是**手动工具**（用户需要手动添加节点、手动推断类型）。我们的差异化是**全自动化**——从扫描到结构推断到代码生成，无需人工干预。

### 可复用组件建议

1. **ReClass.NET 的代码生成器逻辑**：参考其 C++/C# 结构体生成模板，直接复用格式
2. **节点类型系统**：借鉴其节点抽象（Hex8/16/32/64, Int, Float, Double, Vector2/3/4, Matrix, Text, Pointer, VTable）
3. **插件架构**：如果未来要扩展，参考其多语言插件系统

---

## 2. PINCE + libmemscan — 高性能扫描参考（Linux）

**项目**：https://github.com/korcankaraokcu/PINCE

### 核心特点
- Linux 版 "Cheat Engine"，但架构更现代
- 扫描后端用 **Zig 重写**（`libmemscan`），性能数据惊人：

| 测试 | 旧 scanmem | 新 libmemscan | 提升 |
|------|-----------|--------------|------|
| INT32 unknown initial | 14s, 18.3 GiB | 1s, 5.2 GiB | **14x 速度, 3.5x 内存节省** |
| Unknown → exact int32 | 30s, 45.3 GiB transient | 14s, 无瞬态峰值 | **2.1x 速度, 无内存暴涨** |
| FLOAT32 unknown → exact | 14s | 1s | **14x 速度** |

### 关键架构决策（值得参考）

1. **bookkeeping 优化**：
   - scanmem：每扫描字节用 4 字节 bookkeeping → 4GB 内存
   - libmemscan：每字节用 1.03-1.125 字节 bookkeeping → 1GB 内存
   - **启示**：我们的 C++ 扫描引擎也可以优化 bookkeeping 密度

2. **undo 文件持久化**：
   - 旧：tmpfs（RAM）→ 内存压力大
   - 新：`.cache` 目录（磁盘）→ 降低 RAM 使用，有 2s SSD 延迟
   - **启示**：我们的快照系统也可以考虑磁盘持久化，支持大进程扫描

3. **扫描后端独立为库**：
   - `libmemscan` 是独立库，可被任何前端调用
   - 有指针扫描后端（替代了 `libptrscan`）
   - **启示**：我们的 `mg_engine.dll` 应该进一步拆分为 `libmgscan`（扫描库）+ `libmgptr`（指针库）+ `libmgwrite`（写入库）

4. **Keystone 汇编器**：
   - PINCE 使用 **Keystone Engine** 做 on-the-fly 汇编
   - **启示**：我们不需要自研 Assembler，直接集成 Keystone 即可

---

## 3. Ghidra / IDA Pro / Binary Ninja — 静态分析巨头

### 与 MemoryGraph 的关系

这些工具做**静态分析**（分析磁盘上的二进制文件），MemoryGraph 做**动态分析**（分析运行时的内存）。两者互补。

### 可集成组件

| 工具 | 可集成特性 | 集成方式 | 价值 |
|------|----------|----------|------|
| **Ghidra** | 反编译器（Decompiler）+ 数据流分析 | Headless API（Java/Python）| 将运行时断点命中的代码片段送入 Ghidra 反编译，得到高级伪代码 |
| **IDA Pro** | 行业标准的 CFG + 调用图 | IDAPython / Hex-Rays | 将我们的调用栈数据映射到 IDA 的函数名和类型 |
| **Binary Ninja** | 现代 IL（MLIL/HLIL）+ 类型传播 | Python API | 自动化类型推断和结构体重建 |
| **x64dbg** | 开源调试器 + 插件生态 | x64dbgpy / 插件 | 如果我们的断点引擎不够成熟，可以调用 x64dbg 的调试功能 |

### 关键发现：Ghidra Headless 自动化

Ghidra 有强大的 **headless analysis** 模式：
```bash
analyzeHeadless <project_location> <project_name> -import <file> -postScript <script.py>
```

**集成方案**：
1. 我们的断点命中后，提取代码片段（如 1KB 机器码）
2. 将机器码写入临时文件
3. 调用 Ghidra headless 分析，得到：
   - 反编译伪代码（C-like）
   - 控制流图（CFG）
   - 数据流分析（变量定义-使用链）
4. 解析 Ghidra 输出，自动关联到我们的内存变量

**价值**：无需自研反编译器和 CFG/DFG 分析，直接复用 Ghidra 的工业级实现。

---

## 4. 其他相关工具

### scanmem / GameConqueror（Linux）
- 最古老的 Linux 内存扫描工具
- PINCE 已经用 libmemscan 替代了它
- **参考价值低**，已被淘汰

### Frida
- 跨平台动态插桩框架（JavaScript API）
- 可以 hook 函数、追踪调用、修改参数/返回值
- **集成价值**：如果我们的断点/追踪系统不够成熟，可以用 Frida 做补充
- **缺点**：Frida 的 hook 需要知道函数符号或地址，无法自动从内存锚点推导

### TinyInst / DynamoRIO / Intel Pin
- 学术级 DBI（Dynamic Binary Instrumentation）框架
- 可以追踪每条指令的执行
- **集成价值**：用于指令级污点分析（Phase 9）
- **缺点**：性能开销大（600x slowdown），不适合实时分析

---

## 5. 关键差距与差异化定位

### 现有工具的共同缺陷（我们的机会）

| 工具 | 缺陷 | 我们的机会 |
|------|------|-----------|
| ReClass.NET | **纯手动**：用户需要手动添加节点、手动推断类型、手动设置断点 | **全自动**：从扫描到结构推断到代码生成，一键完成 |
| Cheat Engine | **修改导向**：断点只是为了找到地址然后修改，不分析逻辑关系 | **分析导向**：断点是为了构建数据流图和调用图，生成逻辑报告 |
| PINCE | **Linux only**：无 Windows 支持 | **Windows 原生**：x64 C++ DLL，Windows API 直接调用 |
| Ghidra/IDA | **静态分析**：无法分析运行时的内存状态和动态数据结构 | **动态分析**：运行时结构推断，实时追踪变量变化 |
| 所有工具 | **无自动关联**：扫描、断点、反汇编、结构重建是独立的步骤 | **全链路绑定**：内存变量 ↔ 反汇编指令 ↔ 调用栈 ↔ 结构体 ↔ 时序数据，自动关联 |

### 我们的独特定位

> **MemoryGraph 是"动态分析 + 自动推理"的逆向引擎，填补了现有工具的空白。**

- ReClass.NET 告诉你"内存里有什么结构"（手动）
- Cheat Engine 告诉你"怎么修改数值"（手动）
- Ghidra 告诉你"代码逻辑是什么"（静态）
- **MemoryGraph 告诉你"变量和代码的完整关系图谱"（自动）**

---

## 6. 架构优化建议

### 建议 1：扫描引擎独立化（参考 libmemscan）

将 `mg_engine.dll` 拆分为独立库：

```
libmg_scan.dll      # 内存扫描（Exact/Unknown/Between/AOB）
libmg_ptr.dll       # 指针扫描（多级指针链）
libmg_write.dll     # 内存写入 + 指针链写入
libmg_bp.dll        # 断点引擎（硬件/软件/内存保护）
libmg_trace.dll     # 调用栈回溯 + 代码片段提取
libmg_disasm.dll    # 反汇编（Zydis + 可选 Ghidra headless）
```

**好处**：
- 每个库可独立测试和优化
- 可以像 PINCE 的 libmemscan 一样被其他项目复用
- 降低 DLL 体积，按需加载

### 建议 2：集成 Keystone 汇编器

不要自研 Assembler，直接集成 **Keystone Engine**：
- 支持 x86/x64/ARM 等架构
- 支持 Python/C++ 绑定
- 可以 on-the-fly 将汇编文本转为机器码

**用途**：
- 代码注入（Phase 5）
- Speedhack（Hook 时间函数）
- 断点修复（INT3 替换后的原始字节）

### 建议 3：Ghidra Headless 集成（Phase 8+）

对于反编译和静态分析，不要自研，直接调用 Ghidra：

```python
# 伪代码：断点命中后的代码片段分析
import subprocess
import json

def analyze_code_snippet(machine_code_bytes, base_addr):
    # 1. 写入临时文件
    with open("/tmp/snippet.bin", "wb") as f:
        f.write(machine_code_bytes)
    
    # 2. 调用 Ghidra headless 分析
    subprocess.run([
        "analyzeHeadless",
        "/tmp/ghidra_project", "temp_project",
        "-import", "/tmp/snippet.bin",
        "-postScript", "analyze_snippet.py",
        "-scriptPath", "/scripts/"
    ])
    
    # 3. 解析 Ghidra 输出（JSON）
    with open("/tmp/snippet_analysis.json") as f:
        result = json.load(f)
    
    return result  # { functions: [...], decompiled: "...", cfg: {...} }
```

**价值**：
- 无需自研反编译器（节省 6-12 个月开发）
- 直接获得工业级的 CFG、数据流分析、类型推断
- 将 Ghidra 的静态分析结果与我们的动态追踪数据关联

### 建议 4：引入节点类型系统（参考 ReClass.NET）

将当前的"原始地址列表"升级为 ReClass.NET 式的节点系统：

```python
class MemoryNode:
    """ReClass.NET 风格的内存节点"""
    offset: int          # 相对于基址的偏移
    size: int            # 字节大小
    type: NodeType       # HEX8/16/32/64, INT8/16/32/64, FLOAT, DOUBLE, POINTER, VTABLE, TEXT
    name: str            # 推断的字段名（如 "health", "position"）
    value: Any           # 当前值
    is_pointer: bool     # 是否是指针
    children: List[MemoryNode]  # 如果是结构体/指针，子节点
    
    # 动态分析附加信息
    write_insns: List[str]      # 写入该节点的指令地址列表
    read_insns: List[str]       # 读取该节点的指令地址列表
    call_stack: List[str]       # 写入时的调用栈
    temporal_pattern: str       # 时序模式：per-frame / event / timer / noise
    correlation_map: Dict[str, float]  # 与其他节点的相关系数
```

**价值**：
- 从"扁平地址列表"升级到"结构化对象图"
- 直接支持 ReClass.NET 式的代码生成
- 节点自带分析元数据，便于图谱可视化

### 建议 5：快照持久化（参考 PINCE libmemscan）

将快照系统从 RAM 升级到磁盘持久化：

```cpp
// 当前：std::vector<uint8_t> buf((size_t)size);  // 全在 RAM
// 优化：使用内存映射文件或压缩存储

struct DiskSnapshot {
    uint64_t base;
    uint64_t size;
    std::string filepath;  // 如 "snapshot_0x140000000_0x10000.bin"
    uint32_t crc32;        // 校验
};
```

**好处**：
- 支持扫描 64GB+ 进程（如现代游戏）
- 支持"undo"扫描（回退到任意步骤）
- 支持跨会话分析（保存快照，下次加载继续）

---

## 7. 下一步行动建议

### 短期（1-2 周）：断点引擎（Phase 4）
**不要自研**，参考：
- ReClass.NET 的调试器实现（已有 write/access 断点）
- PINCE 的 watchpoint tracking（chained breakpoints）
- x64dbg 的断点系统（开源，可直接读源码）

### 中期（1-2 月）：节点系统 + 代码生成（Phase 5-6）
**参考 ReClass.NET**：
- 直接复用其节点类型定义和代码生成模板
- 将我们的指针链 + DFG 结果自动填入节点系统
- 生成 C++/Python 结构体代码

### 长期（3-6 月）：Ghidra 集成（Phase 8-9）
**不要自研反编译器**：
- 断点命中后，提取代码片段 → Ghidra headless 分析
- 解析 Ghidra 的 CFG/DFG 输出，与我们的动态数据关联
- 生成"反编译伪代码 + 动态变量绑定"的混合报告

### 关键决策：是否复用 ReClass.NET 作为前端？

**方案 A**：将 MemoryGraph 作为 ReClass.NET 的插件（利用其插件系统）
- 优点：复用 ReClass.NET 的成熟 UI 和节点系统
- 缺点：受限于 .NET 平台，我们的 C++ 引擎需要 C++/CLI 包装

**方案 B**：保持独立，但参考 ReClass.NET 的设计
- 优点：保持 Python + C++ 混合架构的灵活性
- 缺点：需要自研 UI 和节点系统

**建议**：方案 B，但将 ReClass.NET 的**节点类型定义**和**代码生成模板**作为参考标准，未来可以导出兼容 ReClass.NET 的文件格式。

---

## 8. 总结

| 调研项 | 结论 |
|--------|------|
| 最接近的项目 | **ReClass.NET**（运行时结构重建，MIT 开源） |
| 最高性能参考 | **PINCE libmemscan**（Zig 实现，14x 速度提升） |
| 最佳静态分析集成 | **Ghidra Headless**（免费，工业级反编译） |
| 最佳汇编器集成 | **Keystone Engine**（支持多架构，Python 绑定） |
| 我们的差异化 | **全自动化**——从扫描到断点到结构推断到代码生成，无需人工干预 |
| 关键建议 | 不要自研反编译器和 Assembler，集成现有工具；将扫描引擎独立为库；引入节点类型系统；快照持久化到磁盘 |
