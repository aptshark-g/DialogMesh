# MemoryGraph 自动化逆向分析引擎 V2 — 完整设计文档

**版本**: 2.0.0-alpha
**日期**: 2026-06-20
**状态**: 设计阶段

---

## 1. 系统概述

### 1.1 目标
构建一个从"内存扫描工具"升级为"自动化逆向分析引擎"的系统，能够：
- **静态分析**目标程序的二进制代码，识别所有内存访问模式
- **动态追踪**关键指令的执行，捕获完整的寄存器上下文
- **自动推断**数据结构布局（结构体字段、偏移、类型）
- **生成报告**包含结构体定义、函数语义、数据流图和AI分析

### 1.2 核心思想
**"从代码出发，追踪数据"** — 不同于传统CE的"从数据出发，猜测代码"：

```
传统方式（CE）:  扫描内存 → 找到地址 → 手动追踪谁写入它
MemoryGraph V2:  分析代码 → 识别所有内存访问 → 动态追踪 → 自动推断结构
```

### 1.3 系统边界

**输入**:
- 目标进程 PID（或自动启动）
- 分析时长（默认 30 秒）
- 策略配置（通用/数值追踪/指针链等）

**输出**:
- 结构体定义（C 风格）
- 函数语义标签（"更新生命值", "计算伤害"等）
- 数据流图（函数 → 结构体 → 字段 → 数值变化）
- AI 分析报告（Markdown 格式）

**不处理**:
- 加壳/混淆代码（需要先脱壳）
- 反调试保护（需要绕过或手动处理）
- 网络/文件 IO 分析（纯内存数据分析）

---

## 2. 架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: 报告与 AI 分析层                                   │
│  - 结构体美化输出                                            │
│  - 函数语义标签生成                                           │
│  - AI Prompt 构建与调用                                        │
│  - Markdown/HTML 报告生成                                     │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: 结构体推断与语义分析层                              │
│  - 偏移聚类分析                                               │
│  - 基址追踪与关联                                             │
│  - 访问频率统计                                               │
│  - 数值变化模式识别（递增/递减/随机）                          │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: 动态追踪层（核心创新）                                │
│  - 指令断点管理（int3 / 硬件断点）                            │
│  - 寄存器上下文捕获（16个通用寄存器）                          │
│  - 调用栈重建（最多 8 层）                                    │
│  - 实际内存地址计算（基址 + 偏移）                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: 静态分析层（核心创新）                               │
│  - 模块枚举与 .text 段定位                                    │
│  - 反汇编引擎（Zydis / 自研）                                 │
│  - 内存访问指令识别与解析                                     │
│  - 指令模式聚类（基址寄存器 + 偏移）                           │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: 基础设施层（复用 V1）                                │
│  - 进程附加/启动                                             │
│  - 内存读写（safe_read / safe_write）                         │
│  - 内存扫描（first_scan / next_scan）                        │
│  - 基础 DFG（节点/边管理）                                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块依赖图

```
                      ┌──────────────┐
                      │  workflow_v2 │
                      │   (工作流)    │
                      └──────┬───────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
  ┌──────────┐        ┌──────────┐          ┌──────────┐
  │ static_  │        │  tracer  │          │  struct_ │
  │ disasm   │───────▶│  (动态)  │─────────▶│ inference│
  │ (静态)   │        │          │          │ (推断)   │
  └──────────┘        └──────────┘          └──────────┘
        │                    │                    │
        │              ┌─────┘                    │
        │              │                          │
        ▼              ▼                          ▼
  ┌──────────┐   ┌──────────┐              ┌──────────┐
  │ pattern_ │   │   int3   │              │   dfg_v2 │
  │ matcher  │   │  handler │              │          │
  └──────────┘   └──────────┘              └──────────┘
        │              │                          │
        │              │                          │
        ▼              ▼                          ▼
  ┌──────────┐   ┌──────────┐              ┌──────────┐
  │  zydis   │   │  debug_  │              │  ai_     │
  │  wrapper │   │  event   │              │  reporter│
  └──────────┘   └──────────┘              └──────────┘
                             │
                             ▼
                      ┌──────────┐
                      │ mg_engine│
                      │  (DLL)   │
                      │  V2 API  │
                      └──────────┘
```

---

## 3. 详细模块设计

### 3.1 Layer 1: 基础设施层（复用 V1）

#### 3.1.1 进程管理（`core/winapi.py`）

**已有接口**（无需修改）:
```python
def OpenProcess(dwDesiredAccess, bInheritHandle, dwProcessId) -> HANDLE
def launch_and_attach(exe_path, args="", working_dir=None) -> (HANDLE, int)
def enum_process_modules(pid) -> List[Dict]  # {name, base, size}
```

**新增接口**:
```python
@dataclass
class ModuleInfo:
    name: str
    base: int
    size: int
    path: str
    sections: List[SectionInfo]  # .text, .data, .rdata

@dataclass
class SectionInfo:
    name: str
    base: int
    size: int
    characteristics: int  # R/W/X flags

def get_module_sections(h_process, module_base) -> List[SectionInfo]:
    """读取 PE 头，解析节表，返回 .text/.data/.rdata 等段信息"""
```

#### 3.1.2 内存扫描（`memory/scanner.py`）

**保留 V1 全部功能**，新增：
```python
def scan_module_text_section(module_base, module_size) -> bytes:
    """读取整个 .text 段到内存，用于静态分析"""
```

### 3.2 Layer 2: 静态分析层

#### 3.2.1 Zydis 集成（`analysis/zydis_wrapper.py`）

**职责**: 封装 Zydis 反汇编库，提供 Python 友好的接口

**Zydis 编译**:
```bash
# Windows (MSVC)
git clone https://github.com/zyantific/zydis.git
cd zydis
mkdir build && cd build
cmake .. -DZYDIS_BUILD_SHARED_LIB=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
# 生成 Zydis.dll + Zydis.lib
```

**Python ctypes 绑定**:
```python
# analysis/zydis_wrapper.py
import ctypes
from ctypes import c_void_p, c_uint64, c_int, c_size_t, POINTER, Structure

class ZydisDecodedInstruction(Structure):
    _fields_ = [
        ("mnemonic", c_int),           # ZydisMnemonic enum
        ("length", c_uint8),
        ("opcode_map", c_uint8),
        ("opcode", c_uint8),
        # ... 更多字段
    ]

class ZydisDecodedOperand(Structure):
    _fields_ = [
        ("id", c_int),                  # 操作数索引
        ("type", c_int),               # REGISTER, MEMORY, IMMEDIATE, etc.
        ("visibility", c_int),          # EXPLICIT, IMPLICIT, etc.
        ("mem_base", c_int),            # 基址寄存器
        ("mem_index", c_int),           # 索引寄存器
        ("mem_scale", c_uint8),         # 缩放因子
        ("mem_disp", c_int64),          # 偏移量
        ("size", c_uint16),             # 操作数大小（位）
    ]

_zydis = ctypes.CDLL("./lib/Zydis.dll")

_zydis.ZydisDecoderDecodeInstruction.argtypes = [
    c_void_p,                       # decoder
    c_void_p,                       # buffer
    c_size_t,                       # buffer length
    POINTER(ZydisDecodedInstruction)
]
_zydis.ZydisDecoderDecodeInstruction.restype = c_int

def decode_instruction(data: bytes, addr: int) -> Optional[Dict]:
    """
    解码单条指令
    
    返回:
        {
            "addr": 0x1234,
            "mnemonic": "mov",
            "length": 5,
            "operands": [
                {
                    "type": "memory",
                    "base_reg": "rbx",
                    "index_reg": None,
                    "scale": 1,
                    "disp": 0x10,
                    "size": 32,  # bits
                },
                {
                    "type": "register",
                    "reg": "eax",
                    "size": 32,
                }
            ],
            "mem_access": {
                "type": "read",  # or "write", "read_write"
                "base_reg": "rbx",
                "disp": 0x10,
                "size": 4,
            }
        }
    """
```

**内存访问检测逻辑**:
```python
# analysis/zydis_wrapper.py

def detect_memory_access(instr: Dict) -> Optional[Dict]:
    """
    判断指令是否包含内存访问，并提取访问模式
    
    支持的指令类型:
        - mov [mem], reg      (write)
        - mov reg, [mem]      (read)
        - mov [mem], imm      (write)
        - add/sub/and/or [mem], reg/imm  (read_write)
        - inc/dec [mem]       (read_write)
        - cmp/test reg, [mem] (read, but no write - skip for tracking)
        - lea reg, [mem]      (address calculation, not actual access - skip)
        - push/pop [mem]      (read/write)
        - xchg [mem], reg     (read_write)
    
    返回 None 如果不是内存访问指令
    """
    mnemonic = instr["mnemonic"]
    operands = instr["operands"]
    
    # 1. 识别操作数类型
    mem_op = None
    reg_op = None
    imm_op = None
    
    for op in operands:
        if op["type"] == "memory":
            mem_op = op
        elif op["type"] == "register":
            reg_op = op
        elif op["type"] == "immediate":
            imm_op = op
    
    if not mem_op:
        return None  # 没有内存操作数
    
    # 2. 判断访问类型
    access_type = None
    
    if mnemonic in ("mov", "movzx", "movsx"):
        # mov [mem], reg/imm -> write
        # mov reg, [mem] -> read
        if mem_op == operands[0]:  # 第一个操作数是内存
            access_type = "write"
        else:
            access_type = "read"
    
    elif mnemonic in ("add", "sub", "and", "or", "xor", "not"):
        # add [mem], reg/imm -> read_write
        access_type = "read_write"
    
    elif mnemonic in ("inc", "dec"):
        # inc [mem] -> read_write
        access_type = "read_write"
    
    elif mnemonic in ("push"):
        # push [mem] -> read (then write to stack, but we care about [mem])
        access_type = "read"
    
    elif mnemonic in ("pop"):
        # pop [mem] -> write
        access_type = "write"
    
    elif mnemonic in ("xchg"):
        # xchg [mem], reg -> read_write
        access_type = "read_write"
    
    elif mnemonic in ("cmp", "test"):
        # cmp [mem], reg -> read (but no modification, skip for structure inference)
        return None
    
    elif mnemonic in ("lea"):
        # lea reg, [mem] -> address calculation only, no actual memory access
        return None
    
    else:
        # 其他指令，保守处理：只要有内存操作数就标记为 read_write
        access_type = "read_write"
    
    return {
        "type": access_type,
        "base_reg": mem_op.get("base_reg"),
        "index_reg": mem_op.get("index_reg"),
        "scale": mem_op.get("scale", 1),
        "disp": mem_op.get("disp", 0),
        "size": mem_op.get("size", 32) // 8,  # bits -> bytes
    }
```

#### 3.2.2 静态分析引擎（`analysis/static_disasm.py`）

**职责**: 扫描整个 .text 段，提取所有内存访问指令，构建指令数据库

**核心类**:
```python
# analysis/static_disasm.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from enum import Enum

class AccessType(Enum):
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"

@dataclass
class MemoryAccessInstruction:
    """内存访问指令的完整描述"""
    # 地址信息
    addr: int                      # 指令地址（RIP）
    module_base: int               # 所属模块基址
    module_name: str               # 所属模块名
    
    # 指令信息
    mnemonic: str                  # 助记符
    length: int                    # 指令长度（字节）
    bytes_hex: str                 # 指令字节序列（hex）
    
    # 内存访问信息
    access_type: AccessType        # 访问类型
    base_reg: Optional[str]        # 基址寄存器（rbx, rbp, rsi, rdi, r13, ...）
    index_reg: Optional[str]       # 索引寄存器（rsi, rdi, r8-r15, ...）
    scale: int                     # 缩放因子（1, 2, 4, 8）
    displacement: int              # 偏移量（0x10, -0x08, ...）
    access_size: int               # 访问大小（1, 2, 4, 8 字节）
    
    # 源/目标操作数
    src_reg: Optional[str]         # 源寄存器（用于 write/read_write）
    dst_reg: Optional[str]         # 目标寄存器（用于 read）
    
    # 函数上下文（可选，启发式识别）
    func_start: Optional[int]      # 函数起始地址
    func_name: Optional[str]      # 函数名（如果有符号）
    
    # 统计信息
    hit_count: int = 0             # 动态追踪命中次数（运行时填充）
    contexts: List[Dict] = field(default_factory=list)  # 动态上下文记录


class StaticDisasmEngine:
    """静态分析引擎"""
    
    def __init__(self, zydis_lib_path: str = "./lib/Zydis.dll"):
        self.zydis = ZydisWrapper(zydis_lib_path)
        self.instructions: List[MemoryAccessInstruction] = []
        self._addr_to_instr: Dict[int, MemoryAccessInstruction] = {}
        
    def analyze_module(self, h_process: int, module_base: int, module_size: int,
                       module_name: str = "unknown") -> List[MemoryAccessInstruction]:
        """
        分析单个模块的 .text 段
        
        流程:
        1. 读取 .text 段原始字节
        2. 逐条反汇编
        3. 识别内存访问指令
        4. 提取访问模式
        5. 尝试函数边界识别（启发式）
        
        返回: 所有内存访问指令列表
        """
        # 1. 读取 .text 段
        text_data = safe_read(module_base, module_size)
        if not text_data:
            return []
        
        # 2. 逐条反汇编
        offset = 0
        while offset < len(text_data):
            instr_data = text_data[offset:offset+15]  # 最长 x86-64 指令 15 字节
            
            decoded = self.zydis.decode_instruction(instr_data, module_base + offset)
            if not decoded:
                offset += 1
                continue
            
            # 3. 检测内存访问
            mem_access = detect_memory_access(decoded)
            if mem_access:
                instr = MemoryAccessInstruction(
                    addr=decoded["addr"],
                    module_base=module_base,
                    module_name=module_name,
                    mnemonic=decoded["mnemonic"],
                    length=decoded["length"],
                    bytes_hex=decoded["bytes"].hex(),
                    access_type=AccessType(mem_access["type"]),
                    base_reg=mem_access["base_reg"],
                    index_reg=mem_access["index_reg"],
                    scale=mem_access["scale"],
                    displacement=mem_access["disp"],
                    access_size=mem_access["size"],
                )
                self.instructions.append(instr)
                self._addr_to_instr[instr.addr] = instr
            
            offset += decoded["length"]
        
        # 4. 函数边界识别（启发式）
        self._identify_function_boundaries()
        
        return self.instructions
    
    def analyze_all_modules(self, h_process: int) -> List[MemoryAccessInstruction]:
        """分析所有已加载模块的 .text 段"""
        all_instrs = []
        for mod in enum_process_modules(GetProcessId(h_process)):
            instrs = self.analyze_module(
                h_process, mod["base"], mod["size"], mod["name"]
            )
            all_instrs.extend(instrs)
        return all_instrs
    
    def _identify_function_boundaries(self):
        """
        启发式识别函数边界
        
        方法:
        1. 寻找 push rbp / mov rbp, rsp 模式（函数序言）
        2. 寻找 leave / ret 模式（函数尾声）
        3. 使用符号表（如果有 PDB）
        """
        # 简化实现：识别常见的函数序言
        for i, instr in enumerate(self.instructions):
            # 简单的启发式：如果指令地址减去模块基址在合理范围内
            # 并且前面有 call 指令引用它，则认为是一个函数入口
            pass
    
    def get_instructions_by_reg(self, reg_name: str) -> List[MemoryAccessInstruction]:
        """获取所有使用特定基址寄存器的指令"""
        return [i for i in self.instructions if i.base_reg == reg_name]
    
    def get_instructions_by_module(self, module_name: str) -> List[MemoryAccessInstruction]:
        """获取特定模块的所有指令"""
        return [i for i in self.instructions if i.module_name == module_name]
    
    def get_instruction_at(self, addr: int) -> Optional[MemoryAccessInstruction]:
        """获取特定地址的指令"""
        return self._addr_to_instr.get(addr)
    
    def export_json(self) -> str:
        """导出所有指令为 JSON（用于调试和持久化）"""
        import json
        data = []
        for i in self.instructions:
            data.append({
                "addr": hex(i.addr),
                "module": i.module_name,
                "mnemonic": i.mnemonic,
                "access_type": i.access_type.value,
                "base_reg": i.base_reg,
                "disp": hex(i.displacement) if i.displacement else 0,
                "size": i.access_size,
                "bytes": i.bytes_hex,
            })
        return json.dumps(data, indent=2)
```

#### 3.2.3 模式聚类引擎（`analysis/pattern_matcher.py`）

**职责**: 将内存访问指令按基址寄存器 + 偏移聚类，识别结构体候选

**核心算法**:
```python
# analysis/pattern_matcher.py

from collections import defaultdict
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass

@dataclass
class OffsetCluster:
    """同一基址寄存器的偏移聚类"""
    base_reg: str
    offsets: Dict[int, List[MemoryAccessInstruction]]  # offset -> [instrs]
    total_accesses: int
    
@dataclass
class StructPattern:
    """结构体访问模式"""
    base_reg: str
    field_offsets: List[int]  # 排序后的偏移列表
    access_types: Dict[int, str]  # offset -> read/write/read_write
    sizes: Dict[int, int]       # offset -> access size
    functions: Set[int]          # 访问该结构体的函数地址
    confidence: float          # 置信度（0-1）
    
    def to_c_struct(self) -> str:
        """生成 C 结构体定义"""
        lines = ["struct UnknownStruct {"]
        for off in sorted(self.field_offsets):
            size = self.sizes.get(off, 4)
            type_str = {1: "uint8_t", 2: "uint16_t", 4: "uint32_t", 8: "uint64_t"}.get(size, "uint32_t")
            lines.append(f"    {type_str} field_{off:02X};  // offset 0x{off:02X}")
        lines.append("};")
        return "\n".join(lines)


class PatternMatcher:
    """模式聚类引擎"""
    
    def __init__(self):
        self.clusters: Dict[str, OffsetCluster] = {}
        self.patterns: List[StructPattern] = []
    
    def cluster_by_register(self, instructions: List[MemoryAccessInstruction]):
        """
        按基址寄存器聚类
        
        算法:
        1. 遍历所有指令
        2. 按 base_reg 分组
        3. 在每个组内，按 displacement 聚类
        4. 统计每个偏移的访问次数和类型
        """
        reg_groups = defaultdict(list)
        
        for instr in instructions:
            if instr.base_reg:
                reg_groups[instr.base_reg].append(instr)
        
        for reg, instrs in reg_groups.items():
            offsets = defaultdict(list)
            for instr in instrs:
                offsets[instr.displacement].append(instr)
            
            self.clusters[reg] = OffsetCluster(
                base_reg=reg,
                offsets=dict(offsets),
                total_accesses=len(instrs)
            )
    
    def identify_struct_patterns(self, min_fields: int = 3,
                                  max_offset: int = 0x1000,
                                  min_confidence: float = 0.5) -> List[StructPattern]:
        """
        识别结构体模式
        
        启发式规则:
        1. 同一基址寄存器访问 >= 3 个不同偏移
        2. 偏移值在合理范围（0 ~ 0x1000）
        3. 偏移之间有规律（4字节对齐、等差数列等）
        4. 被多个函数访问（说明是全局/共享结构）
        5. 读写混合（既有读也有写，说明是活跃数据）
        
        返回: 结构体模式列表（按置信度排序）
        """
        patterns = []
        
        for reg, cluster in self.clusters.items():
            offsets = sorted(cluster.offsets.keys())
            
            # 过滤: 至少 3 个字段，偏移在范围内
            valid_offsets = [o for o in offsets if 0 <= o <= max_offset]
            if len(valid_offsets) < min_fields:
                continue
            
            # 检查对齐: 大部分偏移应该是 4 字节对齐（整数/指针）
            aligned = sum(1 for o in valid_offsets if o % 4 == 0)
            alignment_score = aligned / len(valid_offsets) if valid_offsets else 0
            
            # 收集访问类型和大小
            access_types = {}
            sizes = {}
            functions = set()
            
            for off in valid_offsets:
                instrs = cluster.offsets[off]
                types = set(i.access_type.value for i in instrs)
                access_types[off] = "read_write" if len(types) > 1 else list(types)[0]
                sizes[off] = max(set(i.access_size for i in instrs), key=lambda s: sum(1 for i in instrs if i.access_size == s))
                for i in instrs:
                    if i.func_start:
                        functions.add(i.func_start)
            
            # 置信度计算
            confidence = 0.5
            confidence += 0.1 * len(valid_offsets)  # 字段越多越可能是结构体
            confidence += 0.2 * alignment_score     # 对齐越好越可能是结构体
            confidence += 0.1 * (1 if len(functions) > 1 else 0)  # 多函数访问
            confidence += 0.1 * (1 if any(access_types[o] == "read_write" for o in valid_offsets) else 0)
            confidence = min(confidence, 1.0)
            
            if confidence >= min_confidence:
                patterns.append(StructPattern(
                    base_reg=reg,
                    field_offsets=valid_offsets,
                    access_types=access_types,
                    sizes=sizes,
                    functions=functions,
                    confidence=confidence,
                ))
        
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        self.patterns = patterns
        return patterns
    
    def export_patterns(self) -> str:
        """导出所有结构体模式为文本"""
        lines = ["# 识别的结构体模式", ""]
        for i, p in enumerate(self.patterns[:20], 1):
            lines.append(f"## 结构体 #{i} (置信度: {p.confidence:.2f})")
            lines.append(f"- 基址寄存器: {p.base_reg}")
            lines.append(f"- 字段数: {len(p.field_offsets)}")
            lines.append(f"- 访问函数数: {len(p.functions)}")
            lines.append("")
            lines.append(p.to_c_struct())
            lines.append("")
        return "\n".join(lines)
```

### 3.3 Layer 3: 动态追踪层

#### 3.3.1 C++ DLL 升级（`mg_engine/src/int3_breakpoint.cpp`）

**新增文件**: `mg_engine/src/int3_breakpoint.cpp`

**数据结构设计**:
```cpp
// mg_engine/include/mg_engine_int3.h
#pragma once
#include <stdint.h>
#include <windows.h>

// 寄存器上下文（x86-64）
struct MG_REG_CONTEXT {
    uint64_t rax, rbx, rcx, rdx;
    uint64_t rsi, rdi, rbp, rsp;
    uint64_t r8, r9, r10, r11;
    uint64_t r12, r13, r14, r15;
    uint64_t rip;
    uint32_t eflags;
};

// int3 命中记录
struct MG_INT3_HIT {
    uint64_t bp_addr;           // 断点地址（指令地址）
    uint64_t hit_count;         // 命中次数
    MG_REG_CONTEXT regs;        // 寄存器快照
    uint64_t mem_addr;          // 实际访问的内存地址（计算后的）
    uint64_t old_value;         // 写入前的值（仅写操作）
    uint64_t new_value;         // 写入后的值
    uint64_t timestamp_ms;      // 时间戳
    uint64_t frame_addrs[8];   // 调用栈
    int frame_count;            // 实际栈深度
    char module_name[64];       // 所属模块
};

// int3 断点管理
struct MG_INT3_MANAGER {
    HANDLE hProcess;
    HANDLE hDebugThread;
    bool running;
    
    // 断点列表
    struct Breakpoint {
        uint64_t addr;
        uint8_t original_byte;  // 原始字节（用于恢复）
        bool active;
        int hit_count;
    };
    Breakpoint bps[256];  // 最多 256 个 int3 断点
    int bp_count;
    
    // 命中记录
    MG_INT3_HIT hits[10000];  // 环形缓冲区
    int hit_write_idx;
    int hit_read_idx;
    int total_hits;
};

// API 声明
extern "C" {
    MG_API MG_INT3_MANAGER* MG_CreateInt3Manager(MG_HANDLE h);
    MG_API void MG_DestroyInt3Manager(MG_INT3_MANAGER* mgr);
    
    MG_API int MG_SetInt3Breakpoint(MG_INT3_MANAGER* mgr, uint64_t addr);
    MG_API int MG_ClearInt3Breakpoint(MG_INT3_MANAGER* mgr, uint64_t addr);
    MG_API void MG_ClearAllInt3Breakpoints(MG_INT3_MANAGER* mgr);
    
    MG_API int MG_StartInt3Tracing(MG_INT3_MANAGER* mgr);  // 启动调试线程
    MG_API void MG_StopInt3Tracing(MG_INT3_MANAGER* mgr);
    
    MG_API int MG_GetInt3Hits(MG_INT3_MANAGER* mgr, MG_INT3_HIT* out, int max_count);
    MG_API int MG_GetInt3HitCount(MG_INT3_MANAGER* mgr);
    MG_API void MG_ClearInt3Hits(MG_INT3_MANAGER* mgr);
}
```

**核心实现逻辑**:
```cpp
// mg_engine/src/int3_breakpoint.cpp
#include "mg_engine_int3.h"
#include <cstdio>
#include <cstring>

// int3 指令字节
static const uint8_t INT3_OPCODE = 0xCC;

static DWORD WINAPI DebugThreadProc(LPVOID lpParam) {
    MG_INT3_MANAGER* mgr = (MG_INT3_MANAGER*)lpParam;
    
    DEBUG_EVENT evt;
    while (mgr->running) {
        if (!WaitForDebugEvent(&evt, 100)) {
            continue;  // 超时，检查是否停止
        }
        
        switch (evt.dwDebugEventCode) {
        case EXCEPTION_DEBUG_EVENT: {
            auto& ex = evt.u.Exception;
            if (ex.ExceptionRecord.ExceptionCode == EXCEPTION_BREAKPOINT) {
                uint64_t addr = (uint64_t)ex.ExceptionRecord.ExceptionAddress;
                
                // 查找对应的断点
                for (int i = 0; i < mgr->bp_count; i++) {
                    if (mgr->bps[i].addr == addr && mgr->bps[i].active) {
                        // 1. 恢复原始字节（让指令正常执行）
                        SIZE_T written = 0;
                        WriteProcessMemory(mgr->hProcess, (LPVOID)addr,
                                          &mgr->bps[i].original_byte, 1, &written);
                        
                        // 2. 获取线程上下文（寄存器）
                        HANDLE hThread = OpenThread(THREAD_GET_CONTEXT | THREAD_SET_CONTEXT,
                                                    FALSE, evt.dwThreadId);
                        if (hThread) {
                            CONTEXT ctx;
                            ctx.ContextFlags = CONTEXT_ALL;
                            if (GetThreadContext(hThread, &ctx)) {
                                // 记录命中
                                int idx = mgr->hit_write_idx % 10000;
                                MG_INT3_HIT& hit = mgr->hits[idx];
                                hit.bp_addr = addr;
                                hit.regs.rax = ctx.Rax;
                                hit.regs.rbx = ctx.Rbx;
                                hit.regs.rcx = ctx.Rcx;
                                hit.regs.rdx = ctx.Rdx;
                                hit.regs.rsi = ctx.Rsi;
                                hit.regs.rdi = ctx.Rdi;
                                hit.regs.rbp = ctx.Rbp;
                                hit.regs.rsp = ctx.Rsp;
                                hit.regs.r8 = ctx.R8;
                                hit.regs.r9 = ctx.R9;
                                hit.regs.r10 = ctx.R10;
                                hit.regs.r11 = ctx.R11;
                                hit.regs.r12 = ctx.R12;
                                hit.regs.r13 = ctx.R13;
                                hit.regs.r14 = ctx.R14;
                                hit.regs.r15 = ctx.R15;
                                hit.regs.rip = ctx.Rip;
                                hit.regs.eflags = ctx.EFlags;
                                hit.timestamp_ms = GetTickCount64();
                                
                                // 3. 读取当前指令，计算实际内存地址
                                // 需要反汇编当前指令来解析 [base+disp]
                                // 简化：先记录寄存器，上层 Python 解析
                                
                                // 4. 读取内存值（如果是写操作）
                                // 简化：先记录，上层分析
                                
                                mgr->hit_write_idx++;
                                mgr->total_hits++;
                            }
                            
                            // 5. 设置单步标志（TF），让 CPU 执行完这条指令后再中断
                            ctx.EFlags |= 0x100;  // TF = 1
                            SetThreadContext(hThread, &ctx);
                            CloseHandle(hThread);
                        }
                        
                        // 继续执行（会执行原始指令，然后触发单步异常）
                        ContinueDebugEvent(evt.dwProcessId, evt.dwThreadId, DBG_CONTINUE);
                        
                        // 等待单步异常
                        if (WaitForDebugEvent(&evt, INFINITE)) {
                            if (evt.dwDebugEventCode == EXCEPTION_DEBUG_EVENT &&
                                evt.u.Exception.ExceptionRecord.ExceptionCode == EXCEPTION_SINGLE_STEP) {
                                
                                // 恢复 int3 断点
                                SIZE_T written = 0;
                                WriteProcessMemory(mgr->hProcess, (LPVOID)addr,
                                                  &INT3_OPCODE, 1, &written);
                                
                                ContinueDebugEvent(evt.dwProcessId, evt.dwThreadId, DBG_CONTINUE);
                            }
                        }
                        break;
                    }
                }
            }
            break;
        }
        
        case CREATE_PROCESS_DEBUG_EVENT:
        case EXIT_PROCESS_DEBUG_EVENT:
            mgr->running = false;
            break;
            
        default:
            ContinueDebugEvent(evt.dwProcessId, evt.dwThreadId, DBG_CONTINUE);
            break;
        }
    }
    
    return 0;
}

MG_API MG_INT3_MANAGER* MG_CreateInt3Manager(MG_HANDLE h) {
    MgProcessHandle* mg = mg::_cast_handle(h);
    if (!mg || !mg->hProcess) return nullptr;
    
    MG_INT3_MANAGER* mgr = new MG_INT3_MANAGER();
    memset(mgr, 0, sizeof(*mgr));
    mgr->hProcess = mg->hProcess;
    mgr->bp_count = 0;
    mgr->hit_write_idx = 0;
    mgr->hit_read_idx = 0;
    mgr->total_hits = 0;
    mgr->running = false;
    
    return mgr;
}

MG_API int MG_SetInt3Breakpoint(MG_INT3_MANAGER* mgr, uint64_t addr) {
    if (!mgr || mgr->bp_count >= 256) return -1;
    
    // 读取原始字节
    uint8_t orig = 0;
    SIZE_T read = 0;
    if (!ReadProcessMemory(mgr->hProcess, (LPCVOID)addr, &orig, 1, &read) || read != 1) {
        return -2;
    }
    
    // 写入 int3
    SIZE_T written = 0;
    if (!WriteProcessMemory(mgr->hProcess, (LPVOID)addr, &INT3_OPCODE, 1, &written) || written != 1) {
        return -3;
    }
    
    // 记录
    auto& bp = mgr->bps[mgr->bp_count++];
    bp.addr = addr;
    bp.original_byte = orig;
    bp.active = true;
    bp.hit_count = 0;
    
    return 0;
}

MG_API int MG_StartInt3Tracing(MG_INT3_MANAGER* mgr) {
    if (!mgr || mgr->running) return -1;
    
    // 附加为调试器
    if (!DebugActiveProcess(GetProcessId(mgr->hProcess))) {
        return -2;
    }
    
    mgr->running = true;
    mgr->hDebugThread = CreateThread(nullptr, 0, DebugThreadProc, mgr, 0, nullptr);
    
    return 0;
}
```

**注意**: `int3` 断点需要目标进程被调试器附加（`DebugActiveProcess`），这与当前 CE 式的进程打开（`OpenProcess`）不同。如果目标程序有反调试检测，可能会失败。

**备选方案**（硬件断点 + 选择性设置）:
```cpp
// 如果只设置 4 个硬件断点，不需要 DebugActiveProcess
// 使用 Dr0-Dr3 寄存器
MG_API int MG_SetHardwareBreakpoint(MG_HANDLE h, uint64_t addr, int size, int type) {
    // 1. 枚举所有线程
    // 2. 对每个线程：GetThreadContext -> 设置 Dr0-Dr3
    // 3. SetThreadContext
    // 4. 不需要调试循环，CPU 会自动触发 STATUS_SINGLE_STEP 异常
}
```

#### 3.3.2 Python 追踪管理器（`disasm/tracer_v2.py`）

**职责**: 管理指令断点，解析命中上下文，计算实际内存地址

```python
# disasm/tracer_v2.py

from typing import List, Dict, Optional, Callable
import ctypes
from dataclasses import dataclass
from core import state
from analysis.static_disasm import MemoryAccessInstruction

@dataclass
class TraceContext:
    """动态追踪上下文"""
    bp_addr: int           # 断点地址（指令地址）
    hit_count: int
    
    # 寄存器值
    regs: Dict[str, int]   # {"rax": 0x1234, "rbx": 0x212826A38F0, ...}
    
    # 计算后的内存地址
    mem_addr: int          # 实际访问的内存地址（如 rbx + 0x10 = 0x212826A3900）
    
    # 内存值
    old_value: int         # 写入前（需要读取）
    new_value: int         # 写入后（从寄存器或内存读取）
    
    # 调用栈
    call_stack: List[int]  # [rip, caller, grand_caller, ...]
    
    # 时间戳
    timestamp_ms: int


class InstructionTracer:
    """指令追踪管理器"""
    
    def __init__(self):
        self.mgr = None  # MG_INT3_MANAGER* (ctypes pointer)
        self._callback: Optional[Callable[[TraceContext], None]] = None
        self._target_instrs: Dict[int, MemoryAccessInstruction] = {}  # addr -> instr
        self._hits: List[TraceContext] = []
        
    def setup(self, instructions: List[MemoryAccessInstruction]):
        """
        在关键指令处设置 int3 断点
        
        策略:
        1. 选择每个结构体模式的前 N 个访问指令
        2. 优先选择 write/read_write 指令（更可能有数据变化）
        3. 限制总数不超过 256 个（int3 限制）或 4 个（硬件断点限制）
        """
        if not state.g_mg_handle:
            raise RuntimeError("DLL not loaded")
        
        # 创建 int3 管理器
        self.mgr = mg_engine.MG_CreateInt3Manager(state.g_mg_handle)
        if not self.mgr:
            raise RuntimeError("Failed to create int3 manager")
        
        # 选择关键指令（简化：选择所有 write 指令，限制 256 个）
        selected = []
        for instr in instructions:
            if instr.access_type.value in ("write", "read_write"):
                selected.append(instr)
            if len(selected) >= 256:
                break
        
        # 设置断点
        for instr in selected:
            rc = mg_engine.MG_SetInt3Breakpoint(self.mgr, instr.addr)
            if rc == 0:
                self._target_instrs[instr.addr] = instr
        
        print(f"[Tracer] Set {len(self._target_instrs)} int3 breakpoints")
    
    def start(self, duration_seconds: float, callback: Optional[Callable] = None):
        """启动动态追踪"""
        self._callback = callback
        
        # 启动 int3 追踪
        rc = mg_engine.MG_StartInt3Tracing(self.mgr)
        if rc != 0:
            raise RuntimeError(f"Failed to start int3 tracing: {rc}")
        
        # 后台线程：定期读取命中记录并解析
        import threading
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._collect, args=(duration_seconds,))
        self._thread.start()
    
    def _collect(self, duration_seconds: float):
        """收集命中记录"""
        import time
        start = time.time()
        
        while not self._stop_event.is_set() and time.time() - start < duration_seconds:
            # 读取命中记录
            buf = (mg_engine.MG_INT3_HIT * 1000)()
            n = mg_engine.MG_GetInt3Hits(self.mgr, buf, 1000)
            
            if n > 0:
                for i in range(n):
                    hit = buf[i]
                    self._process_hit(hit)
                
                # 清除已读取的记录
                mg_engine.MG_ClearInt3Hits(self.mgr)
            
            time.sleep(0.1)
    
    def _process_hit(self, hit):
        """解析单个命中记录"""
        bp_addr = hit.bp_addr
        instr = self._target_instrs.get(bp_addr)
        if not instr:
            return
        
        # 提取寄存器值
        regs = {
            "rax": hit.regs.rax, "rbx": hit.regs.rbx, "rcx": hit.regs.rcx,
            "rdx": hit.regs.rdx, "rsi": hit.regs.rsi, "rdi": hit.regs.rdi,
            "rbp": hit.regs.rbp, "rsp": hit.regs.rsp,
            "r8": hit.regs.r8, "r9": hit.regs.r9, "r10": hit.regs.r10,
            "r11": hit.regs.r11, "r12": hit.regs.r12, "r13": hit.regs.r13,
            "r14": hit.regs.r14, "r15": hit.regs.r15,
        }
        
        # 计算实际内存地址
        mem_addr = self._calculate_mem_addr(instr, regs)
        if not mem_addr:
            return
        
        # 读取内存值（如果是写操作）
        old_value = 0
        new_value = 0
        if instr.access_type.value in ("write", "read_write"):
            data = safe_read(mem_addr, instr.access_size)
            if data:
                old_value = int.from_bytes(data, "little")
            
            # 新值通常在 src_reg 中（简化处理）
            if instr.src_reg and instr.src_reg in regs:
                new_value = regs[instr.src_reg] & ((1 << (instr.access_size * 8)) - 1)
        
        ctx = TraceContext(
            bp_addr=bp_addr,
            hit_count=hit.hit_count,
            regs=regs,
            mem_addr=mem_addr,
            old_value=old_value,
            new_value=new_value,
            call_stack=list(hit.frame_addrs[:hit.frame_count]),
            timestamp_ms=hit.timestamp_ms,
        )
        
        self._hits.append(ctx)
        
        if self._callback:
            self._callback(ctx)
    
    def _calculate_mem_addr(self, instr: MemoryAccessInstruction, regs: Dict[str, int]) -> Optional[int]:
        """
        根据指令模式和寄存器值，计算实际内存地址
        
        公式: mem_addr = base_reg + index_reg * scale + displacement
        """
        if not instr.base_reg:
            return None
        
        base = regs.get(instr.base_reg, 0)
        index = regs.get(instr.index_reg, 0) if instr.index_reg else 0
        
        mem_addr = base + index * instr.scale + instr.displacement
        return mem_addr & 0xFFFFFFFFFFFFFFFF  # 64-bit wrap
    
    def stop(self):
        """停止追踪"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        
        if self.mgr:
            mg_engine.MG_StopInt3Tracing(self.mgr)
    
    def get_hits(self) -> List[TraceContext]:
        return self._hits
    
    def get_hit_stats(self) -> Dict:
        """统计命中信息"""
        from collections import Counter
        
        addr_counts = Counter(h.mem_addr for h in self._hits)
        func_counts = Counter(tuple(h.call_stack[:2]) for h in self._hits if h.call_stack)
        
        return {
            "total_hits": len(self._hits),
            "unique_addrs": len(addr_counts),
            "top_addrs": addr_counts.most_common(10),
            "top_funcs": func_counts.most_common(10),
        }
```

### 3.4 Layer 4: 结构体推断与语义分析层

#### 3.4.1 结构体推断引擎（`analysis/struct_inference.py`）

**职责**: 结合静态分析（偏移模式）和动态追踪（实际基址），推断结构体布局

```python
# analysis/struct_inference.py

from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from analysis.static_disasm import StructPattern
from disasm.tracer_v2 import TraceContext

@dataclass
class InferredStruct:
    """推断出的结构体"""
    struct_id: int
    base_addrs: Set[int] = field(default_factory=set)  # 动态追踪发现的基址实例
    pattern: Optional[StructPattern] = None
    
    # 字段（动态完善）
    fields: Dict[int, 'StructField'] = field(default_factory=dict)  # offset -> field
    
    # 访问统计
    total_hits: int = 0
    write_hits: int = 0
    read_hits: int = 0
    
    # 语义标签
    semantic_label: Optional[str] = None  # "Player", "Enemy", "GameState", etc.
    confidence: float = 0.5

@dataclass
class StructField:
    offset: int
    size: int
    type: str
    access_count: int = 0
    write_count: int = 0
    read_count: int = 0
    
    # 数值变化模式
    value_changes: List[Tuple[int, int]] = field(default_factory=list)  # [(old, new), ...]
    value_history: List[int] = field(default_factory=list)
    
    # 语义标签
    semantic_name: Optional[str] = None  # "health", "gold", "score", "level", etc.
    semantic_confidence: float = 0.0


class StructInferenceEngine:
    """结构体推断引擎"""
    
    def __init__(self, patterns: List[StructPattern]):
        self.patterns = patterns
        self.structs: Dict[int, InferredStruct] = {}  # struct_id -> struct
        self._addr_to_struct: Dict[int, InferredStruct] = {}  # base_addr -> struct
        self._next_id = 1
    
    def process_hits(self, hits: List[TraceContext]):
        """
        处理动态追踪命中记录，推断结构体实例
        
        算法:
        1. 对每个命中记录，计算 mem_addr
        2. 从 mem_addr 反推结构体基址: base = mem_addr - offset
        3. 如果 base 已存在，更新对应结构体
        4. 如果 base 不存在，创建新结构体实例
        5. 统计字段访问频率和数值变化模式
        """
        for hit in hits:
            # 找到匹配的指令和偏移
            instr = self._find_instruction(hit.bp_addr)
            if not instr:
                continue
            
            offset = instr.displacement
            base_addr = hit.mem_addr - offset
            
            # 查找或创建结构体
            struct = self._addr_to_struct.get(base_addr)
            if not struct:
                struct = InferredStruct(
                    struct_id=self._next_id,
                    base_addrs={base_addr},
                    pattern=self._find_matching_pattern(instr),
                )
                self._next_id += 1
                self.structs[struct.struct_id] = struct
                self._addr_to_struct[base_addr] = struct
            
            # 更新字段
            if offset not in struct.fields:
                struct.fields[offset] = StructField(
                    offset=offset,
                    size=instr.access_size,
                    type="unknown",
                )
            
            field = struct.fields[offset]
            field.access_count += 1
            
            if instr.access_type.value == "write":
                field.write_count += 1
                field.value_changes.append((hit.old_value, hit.new_value))
            elif instr.access_type.value == "read":
                field.read_count += 1
            else:  # read_write
                field.write_count += 1
                field.read_count += 1
                field.value_changes.append((hit.old_value, hit.new_value))
            
            struct.total_hits += 1
        
        # 分析数值变化模式，推断语义
        self._infer_semantics()
    
    def _infer_semantics(self):
        """
        根据数值变化模式推断字段语义
        
        规则:
        - 数值逐渐递减，且被写入频繁 -> "health" 或 "durability"
        - 数值逐渐递增，且被读取频繁 -> "score" 或 "experience"
        - 数值突然增加（跳跃） -> "gold"（拾取）或 "ammo"（换弹）
        - 数值在 0 和 max 之间波动 -> "ammo" 或 "mana"
        - 数值很少变化，但很重要 -> "level" 或 "rank"
        - 数值是布尔型（0/1） -> "is_alive", "is_active"
        """
        for struct in self.structs.values():
            for offset, field in struct.fields.items():
                if not field.value_changes:
                    continue
                
                # 分析变化模式
                changes = [new - old for old, new in field.value_changes]
                
                # 1. 生命值模式：递减为主，范围 0-1000
                decreases = sum(1 for c in changes if c < 0)
                increases = sum(1 for c in changes if c > 0)
                
                if decreases > increases * 2 and decreases > 3:
                    values = [v for _, v in field.value_changes]
                    if max(values) <= 1000 if values else 0:
                        field.semantic_name = "health"
                        field.semantic_confidence = 0.7
                        continue
                
                # 2. 金币/分数模式：递增为主，偶尔跳跃
                if increases > decreases * 2 and increases > 3:
                    values = [v for _, v in field.value_changes]
                    if any(c > 50 for c in changes):  # 有大额跳跃
                        field.semantic_name = "gold"
                        field.semantic_confidence = 0.6
                    else:
                        field.semantic_name = "score"
                        field.semantic_confidence = 0.6
                    continue
                
                # 3. 弹药/法力模式：在 max 和 0 之间波动
                if len(set(field.value_changes)) > 5:
                    values = [v for _, v in field.value_changes]
                    if values and max(values) <= 100:
                        field.semantic_name = "ammo"
                        field.semantic_confidence = 0.5
                        continue
                
                # 4. 等级模式：很少变化，但递增
                if len(field.value_changes) <= 3 and increases > 0:
                    field.semantic_name = "level"
                    field.semantic_confidence = 0.4
    
    def get_structs_by_confidence(self, min_confidence: float = 0.5) -> List[InferredStruct]:
        """按置信度排序返回结构体"""
        result = [s for s in self.structs.values() if s.confidence >= min_confidence]
        result.sort(key=lambda s: s.confidence, reverse=True)
        return result
    
    def generate_c_header(self, struct: InferredStruct) -> str:
        """生成 C 结构体定义"""
        lines = [f"// Inferred struct (confidence: {struct.confidence:.2f})"]
        if struct.semantic_label:
            lines.append(f"// Semantic: {struct.semantic_label}")
        lines.append(f"struct Struct_{struct.struct_id} {{")
        
        for offset in sorted(struct.fields.keys()):
            field = struct.fields[offset]
            type_map = {1: "uint8_t", 2: "uint16_t", 4: "uint32_t", 8: "uint64_t"}
            type_str = type_map.get(field.size, f"uint32_t /* size={field.size} */")
            
            name = field.semantic_name or f"field_{offset:02X}"
            lines.append(f"    {type_str} {name};  // offset 0x{offset:02X}, "
                        f"accesses: {field.access_count}, "
                        f"writes: {field.write_count}, "
                        f"reads: {field.read_count}")
        
        lines.append("};")
        return "\n".join(lines)
    
    def export_report(self) -> str:
        """生成完整报告"""
        lines = ["# MemoryGraph 自动化逆向分析报告", ""]
        lines.append(f"## 概述")
        lines.append(f"- 推断结构体数: {len(self.structs)}")
        lines.append(f"- 总基址实例数: {len(self._addr_to_struct)}")
        lines.append("")
        
        for struct in self.get_structs_by_confidence():
            lines.append(f"## 结构体 #{struct.struct_id}")
            lines.append(f"- 置信度: {struct.confidence:.2f}")
            lines.append(f"- 基址实例: {len(struct.base_addrs)}")
            lines.append(f"- 总命中: {struct.total_hits}")
            if struct.semantic_label:
                lines.append(f"- 语义标签: {struct.semantic_label}")
            lines.append("")
            lines.append(self.generate_c_header(struct))
            lines.append("")
        
        return "\n".join(lines)
```

### 3.5 Layer 5: 报告与 AI 分析层

#### 3.5.1 AI 报告生成器（`analysis/ai_reporter_v2.py`）

**职责**: 构建结构化 Prompt，调用 AI 分析，生成最终报告

```python
# analysis/ai_reporter_v2.py

from typing import List, Dict
from analysis.struct_inference import InferredStruct, StructInferenceEngine
from core.ai_assistant import KimiCodePromptGenerator

class AIReporterV2:
    """V2 AI 报告生成器"""
    
    def __init__(self, provider: str = "kimi"):
        self.provider = provider
        self.prompt_gen = KimiCodePromptGenerator()
    
    def generate_struct_analysis_prompt(self, engine: StructInferenceEngine) -> str:
        """
        生成结构体分析 Prompt
        
        输入: 结构体推断引擎（包含所有结构体、字段、数值变化模式）
        输出: 结构化 Prompt 文本
        """
        lines = [
            "# 逆向分析任务：识别游戏数据结构",
            "",
            "## 背景",
            "我使用自动化工具分析了一个运行中的程序，追踪了所有内存访问指令，",
            "并捕获了寄存器上下文。基于这些数据，我推断出以下结构体候选。",
            "请帮助确认这些结构体的语义，并给出更准确的字段名。",
            "",
            "## 原始数据",
        ]
        
        for struct in engine.get_structs_by_confidence(min_confidence=0.3):
            lines.append(f"### 结构体 #{struct.struct_id}")
            lines.append(f"- 置信度: {struct.confidence:.2f}")
            lines.append(f"- 动态基址实例: {len(struct.base_addrs)}")
            lines.append(f"- 总访问次数: {struct.total_hits}")
            lines.append("")
            
            lines.append("| 偏移 | 大小 | 访问次数 | 写入 | 读取 | 语义推断 | 数值变化样本 |")
            lines.append("|------|------|----------|------|------|----------|--------------|")
            
            for offset in sorted(struct.fields.keys()):
                field = struct.fields[offset]
                changes_sample = field.value_changes[:5]
                changes_str = ", ".join(f"{old}->{new}" for old, new in changes_sample)
                
                lines.append(
                    f"| 0x{offset:02X} | {field.size} | {field.access_count} | "
                    f"{field.write_count} | {field.read_count} | "
                    f"{field.semantic_name or '?'} ({field.semantic_confidence:.1f}) | "
                    f"{changes_str} |"
                )
            
            lines.append("")
        
        lines.extend([
            "## 任务",
            "1. 请确认每个结构体最可能的语义（Player, Enemy, GameState, Inventory 等）",
            "2. 为每个字段给出更准确的名称（基于数值变化模式）",
            "3. 指出可能的误报（哪些结构体可能是假的）",
            "4. 给出 C 语言结构体定义（包含你的修正）",
            "5. 分析访问频率最高的函数，推断其功能",
            "",
            "## 输出格式",
            "请用以下格式输出：",
            "",
            "```c",
            "// 结构体 1: [你的语义标签]",
            "struct [Name] {",
            "    // ...",
            "};",
            "// 函数分析:",
            "// 0xADDR: [功能描述]",
            "```",
        ])
        
        return "\n".join(lines)
    
    def generate_and_save(self, engine: StructInferenceEngine, output_path: str) -> str:
        """生成报告并保存"""
        prompt = self.generate_struct_analysis_prompt(engine)
        
        # 保存 Prompt（供 Kimi CLI 使用）
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        
        # 如果配置了自动 AI 调用，可以在这里调用 API
        # 但 V2 仍然保持"生成 Prompt + 手动调用"的模式，因为 AI 分析需要时间
        
        return prompt
```

### 3.6 工作流 V2（`core/workflow_engine_v2.py`）

```python
# core/workflow_engine_v2.py

"""
MemoryGraph V2 一键自动化逆向工作流

流程:
1. 枚举模块
2. 静态分析（反汇编 + 模式提取）
3. 指令断点设置（int3 / 硬件断点）
4. 动态追踪（收集寄存器上下文）
5. 结构体推断（偏移聚类 + 语义分析）
6. DFG 构建（函数 → 结构体 → 字段）
7. AI 报告生成
"""

from typing import Dict, List, Any
import time
import threading
from core import state
from analysis.static_disasm import StaticDisasmEngine
from analysis.pattern_matcher import PatternMatcher
from analysis.struct_inference import StructInferenceEngine
from disasm.tracer_v2 import InstructionTracer
from analysis.ai_reporter_v2 import AIReporterV2

class WorkflowEngineV2:
    """V2 自动化逆向工作流引擎"""
    
    def __init__(self):
        self.disasm = StaticDisasmEngine()
        self.matcher = PatternMatcher()
        self.tracer = InstructionTracer()
        self.inference = None
        self.ai = AIReporterV2()
        
        self._running = False
        self._cancelled = False
        self._progress_callback = None
    
    def run(self, duration: float = 30.0) -> Dict[str, Any]:
        """
        运行完整工作流
        
        返回: {"status": "ok", "structs": [...], "report_path": "..."}
        或: {"status": "error", "message": "..."}
        """
        self._running = True
        self._cancelled = False
        
        try:
            # Step 1: 枚举模块
            self._emit_progress("step1", "枚举模块...")
            modules = enum_process_modules(GetProcessId(state.g_hProcess))
            
            # Step 2: 静态分析
            self._emit_progress("step2", "静态分析（反汇编 + 模式提取）...")
            all_instrs = []
            for mod in modules:
                if self._cancelled:
                    return {"status": "cancelled"}
                instrs = self.disasm.analyze_module(
                    state.g_hProcess, mod["base"], mod["size"], mod["name"]
                )
                all_instrs.extend(instrs)
            
            # Step 3: 模式聚类
            self._emit_progress("step3", "模式聚类...")
            self.matcher.cluster_by_register(all_instrs)
            patterns = self.matcher.identify_struct_patterns()
            
            # Step 4: 设置指令断点
            self._emit_progress("step4", f"设置 {len(patterns)} 个结构体模式的指令断点...")
            
            # 选择关键指令：每个结构体前几个 write 指令
            key_instrs = []
            for p in patterns[:10]:  # 最多追踪前 10 个结构体模式
                for off in p.field_offsets[:5]:  # 每个结构体前 5 个字段
                    for instr in self.matcher.clusters[p.base_reg].offsets.get(off, []):
                        if instr.access_type.value in ("write", "read_write"):
                            key_instrs.append(instr)
                            break
            
            self.tracer.setup(key_instrs)
            
            # Step 5: 动态追踪
            self._emit_progress("step5", f"动态追踪 {duration} 秒...")
            self.tracer.start(duration)
            
            # 等待追踪完成
            while self.tracer._thread and self.tracer._thread.is_alive():
                if self._cancelled:
                    self.tracer.stop()
                    return {"status": "cancelled"}
                time.sleep(1)
                stats = self.tracer.get_hit_stats()
                self._emit_progress("step5", f"追踪中... 命中: {stats['total_hits']}, 地址: {stats['unique_addrs']}")
            
            # Step 6: 结构体推断
            self._emit_progress("step6", "结构体推断...")
            self.inference = StructInferenceEngine(patterns)
            self.inference.process_hits(self.tracer.get_hits())
            
            # Step 7: 生成报告
            self._emit_progress("step7", "生成 AI 分析报告...")
            report_path = f"reports/struct_analysis_{int(time.time())}.md"
            self.ai.generate_and_save(self.inference, report_path)
            
            self._emit_progress("done", "完成！")
            
            return {
                "status": "ok",
                "struct_count": len(self.inference.structs),
                "report_path": report_path,
                "patterns": len(patterns),
                "hits": len(self.tracer.get_hits()),
            }
        
        except Exception as e:
            return {"status": "error", "message": str(e)}
        
        finally:
            self._running = False
            if self.tracer:
                self.tracer.stop()
    
    def _emit_progress(self, stage: str, message: str):
        if self._progress_callback:
            self._progress_callback({"stage": stage, "message": message})
    
    def cancel(self):
        self._cancelled = True
```

---

## 4. 数据流设计

### 4.1 静态分析阶段数据流

```
[进程 PID] -> [OpenProcess] -> [枚举模块] -> [读取 .text 段]
                                              -> [Zydis 解码]
                                              -> [识别内存访问指令]
                                              -> [按基址寄存器聚类]
                                              -> [按偏移聚类]
                                              -> [结构体模式候选]
                                              -> [置信度评分]
                                              -> [输出: List[StructPattern]]
```

### 4.2 动态追踪阶段数据流

```
[StructPattern] -> [选择关键指令] -> [MG_SetInt3Breakpoint]
                                              -> [目标程序运行]
                                              -> [int3 触发]
                                              -> [EXCEPTION_BREAKPOINT]
                                              -> [读取线程上下文]
                                              -> [MG_REG_CONTEXT]
                                              -> [计算 mem_addr = base_reg + disp]
                                              -> [读取内存值]
                                              -> [记录 MG_INT3_HIT]
                                              -> [恢复 int3，继续执行]
                                              -> [Python 读取命中记录]
                                              -> [解析为 TraceContext]
                                              -> [输出: List[TraceContext]]
```

### 4.3 结构体推断阶段数据流

```
[TraceContext] -> [mem_addr - offset = base_addr]
                                              -> [查找/创建 InferredStruct]
                                              -> [更新字段访问统计]
                                              -> [记录数值变化]
                                              -> [分析变化模式]
                                              -> [推断语义: health/gold/score/...]
                                              -> [输出: Dict[base_addr, InferredStruct]]
```

### 4.4 报告生成阶段数据流

```
[InferredStruct] -> [生成 C 结构体定义]
                                              -> [构建 AI Prompt]
                                              -> [保存 .md 文件]
                                              -> [（可选）调用 AI API]
                                              -> [输出: Markdown 报告]
```

---

## 5. 接口设计

### 5.1 Python API

```python
# 一键使用
from core.workflow_engine_v2 import WorkflowEngineV2

engine = WorkflowEngineV2()
engine.run(duration=30.0)

# 分步使用
from analysis.static_disasm import StaticDisasmEngine
from analysis.pattern_matcher import PatternMatcher
from disasm.tracer_v2 import InstructionTracer
from analysis.struct_inference import StructInferenceEngine
from analysis.ai_reporter_v2 import AIReporterV2

# 1. 静态分析
disasm = StaticDisasmEngine()
instrs = disasm.analyze_all_modules(h_process)

# 2. 模式聚类
matcher = PatternMatcher()
matcher.cluster_by_register(instrs)
patterns = matcher.identify_struct_patterns()

# 3. 动态追踪
tracer = InstructionTracer()
key_instrs = select_key_instructions(patterns)
tracer.setup(key_instrs)
tracer.start(30.0)

# 4. 结构体推断
inference = StructInferenceEngine(patterns)
inference.process_hits(tracer.get_hits())

# 5. 生成报告
ai = AIReporterV2()
report = ai.generate_and_save(inference, "report.md")
```

### 5.2 C++ DLL API (V2)

```cpp
// mg_engine/include/mg_engine_v2.h

// int3 断点管理
MG_API MG_INT3_MANAGER* MG_CreateInt3Manager(MG_HANDLE h);
MG_API void MG_DestroyInt3Manager(MG_INT3_MANAGER* mgr);
MG_API int MG_SetInt3Breakpoint(MG_INT3_MANAGER* mgr, uint64_t addr);
MG_API int MG_ClearInt3Breakpoint(MG_INT3_MANAGER* mgr, uint64_t addr);
MG_API void MG_ClearAllInt3Breakpoints(MG_INT3_MANAGER* mgr);
MG_API int MG_StartInt3Tracing(MG_INT3_MANAGER* mgr);
MG_API void MG_StopInt3Tracing(MG_INT3_MANAGER* mgr);
MG_API int MG_GetInt3Hits(MG_INT3_MANAGER* mgr, MG_INT3_HIT* out, int max_count);
MG_API int MG_GetInt3HitCount(MG_INT3_MANAGER* mgr);
MG_API void MG_ClearInt3Hits(MG_INT3_MANAGER* mgr);

// 寄存器上下文
MG_API int MG_GetRegContext(MG_INT3_MANAGER* mgr, uint64_t thread_id, MG_REG_CONTEXT* out);

// 调用栈
MG_API int MG_GetCallStack(MG_HANDLE h, uint64_t thread_id, uint64_t* out_addrs, int max_depth, int* out_count);
```

### 5.3 GUI API

```python
# gui/server.py 新增路由

@app.route("/api/v2/analyze/static", methods=["POST"])
def api_v2_static_analyze():
    """启动静态分析"""
    # 返回进度（后台线程）

@app.route("/api/v2/analyze/progress")
def api_v2_analyze_progress():
    """获取分析进度"""

@app.route("/api/v2/structs")
def api_v2_structs():
    """获取推断的结构体列表"""

@app.route("/api/v2/structs/<int:struct_id>")
def api_v2_struct_detail(struct_id):
    """获取结构体详情"""

@app.route("/api/v2/report/generate", methods=["POST"])
def api_v2_generate_report():
    """生成 AI 分析报告"""
```

---

## 6. 性能设计

### 6.1 时间复杂度

| 阶段 | 时间复杂度 | 优化策略 |
|------|----------|----------|
| 读取 .text 段 | O(n) | 按模块并行读取 |
| 反汇编 | O(n) | 使用 Zydis（高性能） |
| 模式聚类 | O(m log m) | m = 内存访问指令数，哈希表加速 |
| int3 命中处理 | O(1) 每命中 | 环形缓冲区，批量读取 |
| 结构体推断 | O(h) | h = 命中数，哈希表查找基址 |

### 6.2 空间复杂度

| 数据 | 空间 | 限制 |
|------|------|------|
| .text 段数据 | ~10-100 MB | 按需读取，不缓存全部 |
| 指令数据库 | ~100K 条 | 每条 ~100 bytes = 10 MB |
| int3 命中记录 | 10000 条环形 | 每条 ~200 bytes = 2 MB |
| 结构体实例 | 无限制 | 依赖目标程序复杂度 |

### 6.3 关键优化

1. **按需反汇编**: 只反汇编包含内存访问指令的函数，而非整个 .text 段
2. **选择性断点**: 不追踪所有指令，只追踪结构体模式的前 N 个字段
3. **批量读取命中**: 每次读取 1000 条记录，减少跨语言调用开销
4. **缓存模块信息**: 模块列表和节信息只读取一次

---

## 7. 错误处理

### 7.1 错误分类

| 错误 | 级别 | 处理策略 |
|------|------|----------|
| 目标进程退出 | 致命 | 立即停止，释放资源 |
| int3 设置失败（地址无效） | 警告 | 跳过该指令，继续 |
| DebugActiveProcess 失败 | 致命 | 回退到硬件断点（4 个） |
| 反解码失败 | 警告 | 跳过 1 字节，继续 |
| 模式聚类无结果 | 警告 | 降低置信度阈值，重试 |
| 动态追踪无命中 | 警告 | 延长追踪时间或更换策略 |
| AI 调用失败 | 非致命 | 保存 Prompt，提示手动调用 |

### 7.2 回退策略

```python
def run_with_fallback():
    # 尝试 int3 断点
    try:
        return run_int3_workflow()
    except DebugAttachError:
        # 回退到硬件断点
        print("[Fallback] int3 failed, using hardware breakpoints (max 4)")
        return run_hardware_bp_workflow()
    except Exception as e:
        # 回退到纯静态分析（无动态追踪）
        print(f"[Fallback] Dynamic tracing failed: {e}")
        return run_static_only_workflow()
```

---

## 8. 测试策略

### 8.1 单元测试

```python
# tests/test_static_disasm.py
class TestStaticDisasm(unittest.TestCase):
    def test_decode_mov_rbx_disp(self):
        # 测试解码 mov [rbx+0x10], eax
        data = bytes([0x89, 0x43, 0x10])  # mov [rbx+0x10], eax
        instr = decode_instruction(data, 0x1000)
        self.assertEqual(instr["mnemonic"], "mov")
        self.assertEqual(instr["operands"][0]["type"], "memory")
        self.assertEqual(instr["operands"][0]["base_reg"], "rbx")
        self.assertEqual(instr["operands"][0]["disp"], 0x10)
    
    def test_detect_write_access(self):
        # 测试识别写操作
        instr = {"mnemonic": "mov", "operands": [{"type": "memory"}, {"type": "register"}]}
        access = detect_memory_access(instr)
        self.assertEqual(access["type"], "write")

# tests/test_pattern_matcher.py
class TestPatternMatcher(unittest.TestCase):
    def test_cluster_by_register(self):
        # 测试聚类
        instrs = [
            MemoryAccessInstruction(addr=0x1000, base_reg="rbx", displacement=0x00, ...),
            MemoryAccessInstruction(addr=0x1005, base_reg="rbx", displacement=0x04, ...),
            MemoryAccessInstruction(addr=0x100A, base_reg="rbx", displacement=0x08, ...),
            MemoryAccessInstruction(addr=0x2000, base_reg="rsi", displacement=0x00, ...),
        ]
        matcher = PatternMatcher()
        matcher.cluster_by_register(instrs)
        
        self.assertEqual(len(matcher.clusters), 2)  # rbx + rsi
        self.assertEqual(len(matcher.clusters["rbx"].offsets), 3)  # 0x00, 0x04, 0x08

# tests/test_struct_inference.py
class TestStructInference(unittest.TestCase):
    def test_infer_health_field(self):
        # 测试推断生命值字段
        hits = [
            TraceContext(mem_addr=0x1000, old_value=100, new_value=95),  # offset 0x00
            TraceContext(mem_addr=0x1004, old_value=95, new_value=90),   # offset 0x00
        ]
        engine = StructInferenceEngine([StructPattern(base_reg="rbx", field_offsets=[0x00])])
        engine.process_hits(hits)
        
        struct = list(engine.structs.values())[0]
        field = struct.fields[0x00]
        self.assertEqual(field.semantic_name, "health")
```

### 8.2 集成测试

```python
# tests/test_workflow_v2.py
class TestWorkflowV2(unittest.TestCase):
    def test_target_game(self):
        # 使用 target_game.py 作为测试目标
        # 1. 启动 target_game
        # 2. 附加进程
        # 3. 运行工作流
        # 4. 验证推断出 health/gold/score 结构体
        pass
```

### 8.3 性能测试

```python
# tests/test_performance.py
class TestPerformance(unittest.TestCase):
    def test_large_module_analysis(self):
        # 测试分析大型模块（如 Unity 游戏引擎）
        # 验证在 1GB .text 段上能在 10 秒内完成
        pass
    
    def test_high_frequency_tracing(self):
        # 测试高频追踪（每秒 1000+ 命中）
        # 验证不丢数据
        pass
```

---

## 9. 实现计划

### Phase 1: 基础设施（第 1 周）
- [ ] 搭建 Zydis 编译环境（Windows MSVC）
- [ ] 实现 `analysis/zydis_wrapper.py`（基础解码 + 内存访问检测）
- [ ] 实现 `analysis/static_disasm.py`（模块扫描 + 指令提取）
- [ ] 单元测试：解码准确性

### Phase 2: 模式分析（第 1-2 周）
- [ ] 实现 `analysis/pattern_matcher.py`（聚类 + 结构体识别）
- [ ] 实现 `analysis/struct_inference.py`（动态追踪 + 语义推断）
- [ ] 集成测试：使用 target_game.py 验证

### Phase 3: C++ DLL 升级（第 2 周）
- [ ] 实现 `mg_engine/src/int3_breakpoint.cpp`（int3 断点 + 寄存器捕获）
- [ ] 实现 `mg_engine/src/hw_breakpoint.cpp`（硬件断点回退）
- [ ] 更新 `mg_engine.h`（V2 API 声明）
- [ ] 编译测试：确保 DLL 加载正常

### Phase 4: 动态追踪（第 2-3 周）
- [ ] 实现 `disasm/tracer_v2.py`（指令断点管理 + 上下文解析）
- [ ] 实现 `core/dfg_v2.py`（结构体级 DFG）
- [ ] 集成测试：验证 int3 命中和寄存器捕获

### Phase 5: 报告与 AI（第 3 周）
- [ ] 实现 `analysis/ai_reporter_v2.py`（Prompt 生成）
- [ ] 实现 `core/workflow_engine_v2.py`（完整工作流）
- [ ] 更新 GUI（新增 V2 标签页）
- [ ] 端到端测试：一键运行 → 结构体报告

### Phase 6: 优化与文档（第 3-4 周）
- [ ] 性能优化（选择性断点、批量读取）
- [ ] 错误处理完善（回退策略）
- [ ] 用户文档（使用指南、API 文档）
- [ ] 集成测试（多个目标程序）

---

## 10. 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| Zydis 编译失败 | 中 | 高 | 备选 Capstone；或自研简单解码器 |
| int3 反调试冲突 | 高 | 高 | 回退到硬件断点；或手动处理反调试 |
| 寄存器上下文捕获性能低 | 中 | 中 | 批量采样；减少断点数量；优化读取频率 |
| 结构体推断误报率高 | 中 | 中 | 结合数值模式过滤；增加置信度阈值；AI 辅助验证 |
| 大型游戏分析超时 | 中 | 低 | 分模块分析；增量分析；限制分析范围 |
| 代码复杂度超出预期 | 高 | 中 | 分阶段交付；先实现 MVP（最小可行产品） |

---

## 11. 附录

### 11.1 术语表

| 术语 | 定义 |
|------|------|
| .text 段 | 可执行代码段，包含所有 CPU 指令 |
| int3 | x86 调试断点指令（0xCC），触发 EXCEPTION_BREAKPOINT |
| 硬件断点 | 使用 Dr0-Dr3 寄存器，最多 4 个，不修改代码 |
| 基址寄存器 | 指令中用于计算内存地址的寄存器（如 rbx, rbp） |
| 偏移量 | 指令中的常量位移（如 [rbx+0x10] 中的 0x10） |
| 结构体推断 | 根据内存访问模式推断数据结构布局 |
| 语义推断 | 根据数值变化模式推断字段含义（health, gold 等） |
| DFG | 数据流图（Data Flow Graph），表示数据在程序中的流动 |

### 11.2 参考资源

- [Zydis GitHub](https://github.com/zyantific/zydis)
- [Capstone Engine](https://www.capstone-engine.org/)
- [Windows Debug API](https://docs.microsoft.com/en-us/windows/win32/debug/debugging-functions)
- [x86-64 指令集参考](https://www.felixcloutier.com/x86/)
- [ReClass.NET](https://github.com/ReClassNET/ReClass.NET) - 结构体分析工具参考
- [Cheat Engine](https://github.com/cheat-engine/cheat-engine) - 内存扫描工具参考

### 11.3 设计决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 反汇编引擎 | Zydis / Capstone / 自研 | Zydis | 轻量、高性能、MIT 协议 |
| 断点类型 | int3 / 硬件 / 软件 | int3 为主，硬件回退 | int3 无限数量，但可能触发反调试 |
| 调试模式 | DebugActiveProcess / OpenProcess | DebugActiveProcess | int3 需要调试器附加 |
| 结构体推断 | 纯静态 / 纯动态 / 混合 | 混合 | 静态识别模式，动态验证基址 |
| AI 集成 | 自动调用 / 生成 Prompt | 生成 Prompt | 避免 API 依赖，用户可手动调用 |

---

*文档结束*
