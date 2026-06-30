# MemoryGraph 自动化逆向分析引擎 — 架构设计文档

## 目标
从"内存扫描工具"升级为"自动化逆向分析引擎"：
- 输入：目标进程
- 输出：结构体定义、函数语义、数据流图、AI 分析报告

## 核心架构（5 层）

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: AI 分析与报告生成                              │
│  输入：结构体定义 + 函数语义 + DFG                        │
│  输出：Markdown 报告（结构体、函数签名、数据关系）         │
├─────────────────────────────────────────────────────────┤
│  Layer 4: 结构体推断与语义分析                             │
│  输入：指令聚类 + 寄存器上下文                            │
│  输出：结构体定义（字段名、偏移、类型）、函数语义标签       │
├─────────────────────────────────────────────────────────┤
│  Layer 3: 动态追踪（指令断点 + 寄存器快照）               │
│  输入：静态分析识别的关键指令                             │
│  输出：命中记录（RIP + 寄存器值 + 内存地址 + 调用栈）     │
├─────────────────────────────────────────────────────────┤
│  Layer 2: 静态分析（反汇编 + 模式提取）                    │
│  输入：目标模块的 .text 段                                │
│  输出：所有内存访问指令（基址寄存器 + 偏移 + 操作类型）   │
├─────────────────────────────────────────────────────────┤
│  Layer 1: 进程管理与模块枚举                               │
│  输入：PID                                                │
│  输出：模块列表、.text/.data/.rdata 段地址范围            │
└─────────────────────────────────────────────────────────┘
```

## 实现路线图（5 个 Phase）

### Phase A: 静态分析引擎（2-3 天）
- [ ] `analysis/static_disasm.py`：扫描 .text 段，提取内存访问指令
- [ ] `analysis/pattern_matcher.py`：指令模式聚类，识别结构体候选
- [ ] `analysis/struct_inference.py`：基于偏移聚类推断结构体布局

### Phase B: C++ DLL 升级（2-3 天）
- [ ] 新增 `MG_SetInstructionBreakpoint`（指令断点，不是内存断点）
- [ ] 断点触发时捕获寄存器上下文（rax, rbx, rcx, rdx, rsi, rdi, rbp, rsp）
- [ ] 新增 `MG_GetHitContext`（返回寄存器快照 + 实际内存地址）

### Phase C: 动态追踪引擎（1-2 天）
- [ ] `disasm/tracer.py`：指令断点管理（设置/清除/回调）
- [ ] `analysis/context_analyzer.py`：解析寄存器值，计算实际内存地址

### Phase D: DFG 升级（1-2 天）
- [ ] `core/dfg.py`：从"指令→内存"升级为"函数→结构体→字段→数值"
- [ ] 新增结构体节点、字段边、函数调用边

### Phase E: 工作流重构（1-2 天）
- [ ] `core/workflow_engine_v2.py`：新工作流（静态分析 → 指令断点 → 动态追踪 → 结构体推断 → AI 报告）
- [ ] GUI 更新：新增"静态分析"标签页，显示结构体候选

## 技术选型

### 反汇编引擎
- **方案 1**：集成 Zydis（轻量、高性能、MIT 协议）
- **方案 2**：集成 Capstone（功能全、但较重）
- **方案 3**：自研简单 x86-64 解码器（仅支持 mov/add/sub 等常见指令）

推荐 **方案 1（Zydis）** + **方案 3（自研 fallback）**：
- Zydis 处理复杂指令
- 自研处理常见模式（mov [rbx+0x10], eax）

### 指令断点实现
- x86-64：使用 `int3`（0xCC）软件断点
  - 优点：无限数量（不限制 4 个硬件断点）
  - 缺点：需要修改代码，可能触发反调试
- 备选：使用 Intel PT（Processor Trace）或 AMD BTM
  - 优点：无侵入
  - 缺点：需要驱动级支持，复杂度高

**第一阶段使用 `int3` 软件断点**。

### 寄存器上下文捕获
- 断点触发时，Windows 发送 `EXCEPTION_DEBUG_EVENT`
- 在异常处理中获取线程上下文：`GetThreadContext(hThread, &ctx)`
- 从 `CONTEXT` 结构读取寄存器值

## 数据结构设计

### 内存访问指令（Layer 2 输出）
```python
@dataclass
class MemoryAccess:
    addr: int           # 指令地址（RIP）
    type: str           # "read" | "write" | "read_write" | "modify"
    base_reg: str       # 基址寄存器（"rbx", "rbp", "rsi", "rdi", "r13", ...）
    index_reg: str      # 索引寄存器（可选，用于 [rbx+rsi*4]）
    scale: int          # 缩放因子（1, 2, 4, 8）
    displacement: int   # 偏移量（0x10, -0x08, ...）
    size: int           # 访问大小（1, 2, 4, 8）
    mnemonic: str       # 指令助记符（"mov", "add", "sub", ...）
    module: str         # 所属模块名
    func_start: int     # 函数起始地址（可选，通过符号或启发式）
```

### 结构体候选（Layer 4 输出）
```python
@dataclass
class StructCandidate:
    base_addrs: Set[int]      # 可能的结构体基址（来自动态追踪）
    fields: List[StructField] # 字段列表
    access_funcs: Set[int]    # 访问该结构体的函数地址
    confidence: float         # 置信度

@dataclass
class StructField:
    offset: int       # 偏移量
    size: int         # 大小（1, 2, 4, 8）
    type: str         # "int", "float", "pointer", "unknown"
    access_count: int # 访问次数
    read_funcs: Set[int]   # 读取该字段的函数
    write_funcs: Set[int]  # 写入该字段的函数
    name_guess: str   # AI 推断的字段名（如 "health", "gold"）
```

### 命中上下文（Layer 3 输出）
```c
typedef struct {
    uint64_t rip;           // 触发指令地址
    uint64_t rax, rbx, rcx, rdx, rsi, rdi, rbp, rsp;  // 寄存器
    uint64_t r8, r9, r10, r11, r12, r13, r14, r15;    // 扩展寄存器
    uint64_t mem_addr;      // 实际访问的内存地址（计算后的 [base_reg + disp]）
    uint64_t old_value;     // 写入前的值
    uint64_t new_value;     // 写入后的值
    uint64_t timestamp_ms;  // 时间戳
    uint64_t frame_addrs[8]; // 调用栈（8 层）
    int frame_count;        // 实际栈深度
    char module_name[64];   // 所属模块
} MG_HIT_CONTEXT;
```

## 工作流 V2（一键自动化逆向）

```python
def run_v2_workflow():
    # Step 1: 枚举模块
    modules = enum_modules()
    
    # Step 2: 静态分析每个模块的 .text 段
    all_accesses = []
    for mod in modules:
        accesses = static_analyze_module(mod.base, mod.size)
        all_accesses.extend(accesses)
    
    # Step 3: 模式聚类，识别结构体候选
    structs = cluster_access_patterns(all_accesses)
    
    # Step 4: 选择关键指令设断点（指令断点，不是内存断点）
    key_instructions = select_key_instructions(structs)
    for instr in key_instructions:
        set_instruction_breakpoint(instr.addr, on_hit)
    
    # Step 5: 运行目标程序，收集寄存器上下文
    run_target_for(duration=30)
    
    # Step 6: 动态分析：结合寄存器值反推结构体基址
    hits = get_hits_with_context()
    for hit in hits:
        # 从 hit.rbx + hit.instr.displacement 计算实际地址
        base_addr = hit.rbx  # 假设基址在 rbx
        struct = find_struct_by_base(structs, base_addr)
        if struct:
            field = struct.find_field_by_offset(hit.instr.displacement)
            record_access(struct, field, hit)
    
    # Step 7: 构建 DFG：函数 → 结构体 → 字段 → 数值变化
    dfg = build_struct_dfg(hits, structs)
    
    # Step 8: AI 分析：生成结构体定义 + 函数语义
    ai_report = generate_struct_analysis(dfg, structs)
    
    return ai_report
```

## 风险与备选方案

| 风险 | 影响 | 备选方案 |
|------|------|----------|
| `int3` 断点触发反调试 | 高 | 使用硬件断点（限制 4 个）+ 选择性设置 |
| 自研解码器不支持复杂指令 | 中 | 集成 Zydis |
| 寄存器上下文捕获性能低 | 中 | 批量采样，非逐条记录 |
| 结构体推断误报率高 | 中 | 结合数值变化模式（health 递减、gold 递增）过滤 |

## 下一步行动

1. **先验证 Zydis 集成可行性**：在 Windows 上编译 Zydis，测试解码简单指令
2. **升级 C++ DLL**：新增 `int3` 指令断点 + 寄存器上下文捕获
3. **实现静态分析 Python 层**：扫描 `.text` 段，提取内存访问模式
4. **重构工作流**：串联所有模块

这是一个 **2-3 周的全职开发工作量**（假设每天 4-6 小时）。当前代码需要保留作为底层基础设施（内存扫描、DLL 加载、基础 DFG），但上层分析逻辑需要完全重写。

---
*生成时间：2026-06-20*
*作者：MemoryGraph Architecture Team*
