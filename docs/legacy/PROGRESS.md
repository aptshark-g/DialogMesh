# MemoryGraph 开发进度报告

## 项目概述

MemoryGraph 是一个 Windows 内存分析工具，基于 Python 编排层 + C++ x64 引擎实现，功能对标 Cheat Engine。支持精确值扫描、未知初始值、范围扫描、字节数组特征码、多级指针链、时序追踪、反汇编、内存断点、数据流图等完整工作流。

---

## 完成阶段

### Phase 0: C++ DLL 骨架 + Python ctypes 加载 ✅

- [x] 创建 mg_engine.dll 项目结构（CMake + MSVC 2019）
- [x] 定义 C API 头文件（mg_engine.h）供 ctypes 共享
- [x] 实现版本查询、错误处理、文件日志系统
- [x] Python DLL 加载器（core/dll_loader.py）自动加载 + 降级回退
- [x] 热降级机制：DLL 缺失时自动回退到纯 Python 实现

### Phase 1: 扫描引擎 C++ 优化 ✅

- [x] 精确值扫描（Exact）：memchr 预筛选 + 对齐批量比较
- [x] 未知初始值扫描（Unknown）：对齐地址批量记录
- [x] 范围扫描（Between）：整数/浮点范围比较
- [x] 字节数组扫描（Byte Array）：特征码 + 通配符掩码比较
- [x] 再次扫描（Next Scan）：快照对比 + 批量读取优化
- [x] 优化细节：1字节 memchr、2/4/8字节对齐比较、通用模式 memchr+memcmp

### Phase 2: 指针扫描 C++ 优化 ✅

- [x] 多级指针链发现（1-8 级）：base + offset -> [*ptr] + offset -> ... -> target
- [x] Bulk-read 内存快照：一次性读取所有可读区域
- [x] 模块二分查找：快速判断指针位于模块（静态基址）或堆（heap）
- [x] 智能 4GB 对齐块范围：64位高位地址自动收缩扫描范围
- [x] CE 语义兼容：base_offset 存储 ptr_val（解引用后的值）

### Phase 3: 写内存引擎 + 模糊匹配 ✅

- [x] 直接地址写入：WriteProcessMemory + 自动绕过页面保护
- [x] 指针链写入：MG_WritePointerChain 自动解析多级偏移
- [x] 批量读取优化：MG_ReadMultiFast 合并相邻地址读取
- [x] 模糊匹配：指针链写入支持 Between、Unknown、ByteArray 模式

### Phase 4: 时序追踪 + 数据分析 ✅

- [x] 高速采样：10ms 间隔多地址并行读取
- [x] ECharts 时序曲线：数值随时间变化可视化
- [x] 数据依赖关联图：力导向图展示地址间相关性
- [x] 自动分类：常量 / 周期 / 交互 / 噪声
- [x] 因果关联计算：实线=因果，虚线=相关

### Phase 5: 调试器集成 ✅

- [x] 内存断点：监控指定地址的读/写/读写访问
- [x] 指令追踪：记录执行流中的指令级操作
- [x] 调用栈捕获：断点命中时记录调用栈帧
- [x] 代码上下文：断点命中时记录前后 64 字节代码
- [x] 两种实现模式：
  - Debug Register 模式：使用 DR0-DR3 硬件断点（最多 4 个）
  - Guard Page 模式：使用 VirtualProtect 模拟（数量不限，但速度较慢）

### Phase 6: 数据流图 (DFG) + AI 逆向分析 ✅

- [x] DFG 图构建：节点=地址，边=数据依赖
- [x] 断点命中同步：自动将断点命中记录导入 DFG
- [x] 图分析报告：生成 JSON 格式的 DFG 报告
- [x] Kimi Code CLI 集成：
  - [x] Prompt Generator 模式：GUI 生成 markdown prompt，用户复制到 Kimi CLI 终端执行
  - [x] CLI 入口点：cli.py 支持 8 个子命令（attach/scan/next/build/analyze/explain/fix/reverse）
  - [x] PowerShell 脚本：scripts/kimi-analyze.ps1、scripts/kimi-fix.ps1
  - [x] 使用文档：docs/KIMI_CLI.md

---

## 技术修复记录

### Phase 6 修复（Kimi Code 集成）

**问题 1**：Kimi Code API Key 无法用于直接 REST API 调用
- 现象：HTTP 403 Forbidden，提示 "only available for Coding Agents"
- 解决：改为 Prompt Generator 模式，生成 markdown prompt 让用户通过 Kimi CLI 终端执行
- 涉及文件：core/ai_assistant.py、gui/server.py、gui/templates/index.html

**问题 2**：MG_BP_HIT 结构体缺少 watched_addr 字段
- 现象：debugger.py 无法从 hit 记录中提取监控地址
- 解决：在 MG_BP_HIT 结构体中添加 watched_addr 字段（256字节总大小）
- 涉及文件：mg_engine/include/mg_engine.h、mg_engine/src/breakpoint.cpp

**问题 3**：MG_ClearBreakpointHits API 缺失
- 现象：断点命中记录无法清除，导致 DFG 同步后重复数据
- 解决：在 mg_engine.h 和 breakpoint.cpp 中实现 MG_ClearBreakpointHits 函数
- 涉及文件：mg_engine/include/mg_engine.h、mg_engine/src/breakpoint.cpp

**问题 4**：Guard Page 模式缓冲区溢出
- 现象：读取断点地址的值时可能超出缓冲区边界
- 解决：限制 read_size = min(bp_size, 8)，确保不超过 val_buf[64]
- 涉及文件：mg_engine/src/breakpoint.cpp

---

## 文件清单

### C++ 引擎（mg_engine/）

| 文件 | 说明 | 状态 |
|------|------|------|
| src/api.cpp | 版本、错误、日志系统 | ✅ |
| src/attach.cpp | 进程附加、64位检测 | ✅ |
| src/scanner.cpp | 扫描引擎（Exact/Unknown/Between/ByteArray/NextScan） | ✅ |
| src/scanner_opt.cpp | 优化算法（memchr、对齐、批量读取） | ✅ |
| src/pointer.cpp | 多级指针扫描（bulk snapshot、智能4GB块） | ✅ |
| src/write.cpp | 指针链写入、合并批量读取 | ✅ |
| src/tracker.cpp | 追踪采样 | ✅ |
| src/disasm.cpp | 反汇编 | ✅ |
| src/breakpoint.cpp | 断点、基础读写、Guard Page | ✅ |
| include/mg_engine.h | 公共 API 头（ctypes 共享） | ✅ |
| include/mg_engine_internal.h | 内部辅助 | ✅ |
| include/mg_engine_opt.h | 扫描优化函数声明 | ✅ |

### Python 核心层（core/）

| 文件 | 说明 | 状态 |
|------|------|------|
| state.py | 全局状态（进程句柄、扫描结果、追踪数据） | ✅ |
| winapi.py | Windows API ctypes 封装 | ✅ |
| dll_loader.py | mg_engine.dll 加载 + 结构体/函数绑定 | ✅ |
| debugger.py | 调试器集成（断点、追踪、DFG 同步） | ✅ |
| dfg.py | 数据流图构建与分析 | ✅ |
| ai_assistant.py | Kimi Code Prompt Generator | ✅ |

### GUI 层（gui/）

| 文件 | 说明 | 状态 |
|------|------|------|
| server.py | Flask REST API 路由 | ✅ |
| templates/index.html | 单页应用（标签页：CE功能/Hex/指针/时序/反汇编/Kimi CLI） | ✅ |

### CLI 工具

| 文件 | 说明 | 状态 |
|------|------|------|
| cli.py | 命令行入口（8 个子命令） | ✅ |
| scripts/kimi-analyze.ps1 | PowerShell 分析脚本 | ✅ |
| scripts/kimi-fix.ps1 | PowerShell 修复脚本 | ✅ |

### 文档

| 文件 | 说明 | 状态 |
|------|------|------|
| docs/KIMI_CLI.md | Kimi Code CLI 集成指南 | ✅ |
| .env.example | 环境配置示例 | ✅ |
| README.md | 项目说明 | ✅ |
| PROGRESS.md | 本文件 | ✅ |

---

## 构建状态

- **编译器**：Visual Studio 2019 Community (MSVC 14.29, v142 toolset)
- **Windows SDK**：10.0.19041
- **CMake**：3.16+
- **DLL 大小**：~80KB（Release x64）
- **编译结果**：0 error, 0 warning
- **部署方式**：MSBuild 编译后复制到项目根目录（旧 DLL 重命名为 .bak）

---

## 已知限制

1. **管理员权限**：扫描和写入其他进程内存需要以管理员身份运行
2. **64-bit 目标**：主要针对 64 位进程优化，32 位支持未经充分测试
3. **UTF-8 编码**：C++ 源文件使用纯 ASCII（无中文/全角符号），避免 MSVC GBK 代码页报错
4. **DLL 热替换**：旧 DLL 被 Python 进程占用时无法直接覆盖，需先重命名旧文件再复制新文件
5. **CMake 重配置**：某些环境下 VS2019 路径检测失败，推荐直接 `touch` stamp 文件后使用 MSBuild 编译 `.vcxproj`
6. **Kimi Code API**：API Key 仅适用于 Kimi CLI 终端工具，不支持直接 REST API 调用

---

*最后更新：2026-06-15*
