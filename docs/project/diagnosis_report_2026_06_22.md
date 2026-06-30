# MemoryGraph 系统问题诊断与修复方案报告

**生成时间**: 2026-06-22  
**目标进程**: HipsDaemon.exe (火绒 HIPS 主动防御模块)  
**程序类型**: security (修正后) / unknown (当前 bug 表现)  
**问题等级**: 架构级缺陷 + 数据流断裂 + 工作流缺失关键环节

---

## 1. 问题清单（Bug 与设计缺陷）

### 1.1 数据流断裂：键名不匹配

| 层级 | 生产者 | 消费者 | 问题 |
|------|--------|--------|------|
| 推断层 | `ProcessProfiler.infer()` 返回 `"cat"` | `workflow_engine` 读取 `"type"` | 类型信息丢失，始终显示 `unknown` |
| 配置层 | `PROFILES` 使用 `"value_range"` | `AddressSelector` 读取 `"score_range"` | 数值范围不匹配，评分失效 |

**影响**: HipsDaemon 实际已匹配到 `security` 类别，但界面显示 `unknown`；`score_value` 无法获取正确范围，所有地址默认置信度 50%。

### 1.2 工作流缺失：无 Next Scan 过滤

`first_scan_unknown()` 将进程**全部内存空间**的每一个对齐地址存入 `g_scanAddrs`（数量级：10^7 ~ 10^9）。Workflow 直接取前 100 个：

```python
for addr in state.g_scanAddrs[:100]:   # 取前 100 个 → 全是 PE 头/导入表
```

**后果**: 选中的地址是 `mdnsNSP.dll+0x0` 到 `+0x24`（DLL 文件头区域），这些地址：
- 存放的是 PE 头字段（Magic、Timestamp、PointerToSymbolTable），运行时**不会变化**
- 断点命中数 = 0（预期内）
- DFG 节点数 = 0，边数 = 0

### 1.3 地址选择策略：未排除无效区域

未区分内存区域类型：
- 代码段（`.text`）：可执行，但数值通常是指令编码，无意义
- PE 头/导入表：文件映射区，运行时只读
- 堆栈（`.stack`）：临时数据，变化快但生命周期短
- 堆（`.heap`）：动态分配，最有价值的目标区域
- BSS/Data（`.data`, `.bss`）：全局变量，静态数据

### 1.4 AI 分析层：零数据幻觉

当 `total_nodes == 0` 且 `total_hits == 0` 时，AI 未拒绝分析，而是**编造**了：
- 音频处理伪代码（`get_audio_stream()`, `FFT`, `AAC`）
- 与 HipsDaemon（安全防御）完全无关的领域假设

**根本原因**: prompt 未设置硬性约束 — "数据不足时直接拒绝，禁止推测"。

### 1.5 进程类型推断：未传入 Profile 到选择器

```python
# workflow_engine.py 第 510 行
self._selector = AddressSelector(pipeline_config)   # 未传 profile！
```

`AddressSelector` 默认使用 `ProcessProfiler.infer("")` → `unknown` 配置，导致类型感知评分完全失效。

---

## 2. 相关论文与工具调研

### 2.1 Cheat Engine 内存扫描算法（Unknown Initial Value）

**来源**: Cheat Engine 官方文档 / Fandom Wiki / CSDN 教程  
**核心机制**:

```
First Scan (Unknown Initial Value)
    → 存储所有地址（~10^9 个）
    → 等待用户操作（如：掉血、增加金币）
Next Scan #1 (Decreased Value / Increased Value / Changed / Unchanged)
    → 对比当前值与快照，过滤不符合条件的地址
Next Scan #2 (重复)
    → 通常 3-5 轮后缩小到 10^1 ~ 10^2 个地址
Next Scan #3 (Exact Value 或范围确认)
    → 最终确定目标地址
```

**关键启示**:
- 未知初值扫描**本身不产生可用地址**，只是建立候选集
- **必须**配合变化过滤（Next Scan）才能缩小范围
- 轮询策略（Changed/Unchanged）适用于不知道值如何变化的情况

### 2.2 PIN / DynamoRIO — 动态二进制插桩（DBI）

**来源**: Intel PIN 官方文档 / DynamoRIO 教程 / 博客 "Binary Translation (PIN & DynamoRIO)"  
**核心能力**:
- **指令级插桩**: 在每条指令执行前后插入探针代码
- **内存追踪**: `INS_IsMemoryRead`/`INS_IsMemoryWrite` 追踪所有内存访问
- **DFG 构建**: 从指令 trace 中提取数据依赖关系（def-use chain）
- **典型应用**: MallocTracer（追踪堆分配/释放，检测 double free / memory leak）

**对 MemoryGraph 的启示**:
- 我们的 DFG 当前为 0 节点，是因为没有实际指令 trace
- 使用 DBI（如 PIN）或更轻量的方案（如 ours: 断点/guard page + Zydis 反汇编）可以捕获真实数据流
- 无需全量插桩，可只对**选中地址的读写指令**做断点触发 + 反汇编

### 2.3 SDFT — 基于 PDG 的高效动态数据流跟踪

**来源**: arXiv, "Sdft: A PDG-based Summarization for Efficient Dynamic Data Flow Tracking"  
**核心思想**:
- **混合粒度**: 函数级抽象摘要 + 指令级精确追踪
- **库函数摘要**: 预计算标准库函数（glibc）的 taint 传播规则
- **性能优化**: 相比纯 Libdft 提升 1.58x 速度

**启示**: 我们的 DFG 构建可以借鉴"摘要 + 精确"的混合策略 — 对已知模块（如系统 DLL）使用预定义摘要，对目标进程代码做精确反汇编。

### 2.4 LATTE — LLM 辅助二进制污点分析

**来源**: arXiv, "Harnessing the Power of LLM to Support Binary Taint Analysis"  
**核心贡献**:
- **自动化 taint 规则推断**: 无需人工定制传播规则，LLM 自动从二进制代码推断
- **漏洞检测**: 在真实固件中发现 37 个新 bug，7 个分配 CVE
- **低成本**: 相比传统方案工程开销显著降低

**启示**: 我们的 AI 分析层可以学习 LATTE 的"数据驱动"方式 — 不依赖预定义模板，而是让 LLM 从实际 trace 中推断语义，但前提是**必须有足够数据**。

### 2.5 XAI + EDR — 可解释 AI 反向分析

**来源**: TechScience, "Reverse Analysis Method and Process for Improving Malware Detection Based on XAI Model"  
**核心方法**:
- **XGBoost + SHAP**: 识别影响恶意软件分类的关键参数
- **反向分析**: 从检测结果回溯到具体特征贡献
- **关键发现**: `OrganizationIdentifier` 影响值 +0.67，`CityIdentifier` +0.36

**启示**: 我们的 `score_value` 可以采用类似 SHAP 的"特征贡献"思想，为每个地址分配"类型贡献度"，而非简单置信度。

### 2.6 AMAL — 自动化恶意软件分析平台

**来源**: alrawi.io, "High-fidelity, behavior-based automated malware analysis"  
**核心架构**:
- **AutoMal**: 虚拟化环境中运行样本，收集内存/文件/注册表/网络 artifacts
- **MaLabel**: 从 artifacts 提取特征向量，SVM/决策树分类
- **特征维度**: 静态 opcode 序列 + 动态 API 调用 + 文件操作 + 网络行为

**启示**: 进程类型推断可以结合**静态签名**（YARA）+ **动态行为**（API hook 序列），而非仅依赖进程名。

### 2.7 华为 HiSec Endpoint — 商用 EDR 实践

**来源**: 华为官方产品文档  
**关键能力**:
- **Key memory scanning**: 关键内存扫描 + 静态分析 + 动态行为模拟
- **AI 行为分析**: 第三代 AI 杀毒引擎，基于华为 SiteAI 平台
- **内存级图引擎**: 基于内存的图引擎检测无文件攻击和零日漏洞
- **检测率**: 已知勒索软件 100%，零日漏洞利用 95%+

**启示**: 安全软件的内存分析重点在于**行为模式**（API 序列、内存注入、指令序列），而非静态数值。HipsDaemon 的监控数据（文件/注册表/网络操作计数）是更好的分析目标。

---

## 3. 修复方案

### 3.1 立即修复（Bug 修复层，预计 1-2 小时）

#### 修复 A: 统一键名
```python
# reverse_pipeline.py
# 将 PROFILES 中所有 "value_range" 改为 "score_range"（或反之统一）
# 将 infer() 返回的 "cat" 改为 "type"（或所有消费者改为 "cat"）
```

#### 修复 B: 传入 Profile 到 AddressSelector
```python
# workflow_engine.py
profile = ProcessProfiler.infer(process_name)
self._selector = AddressSelector(pipeline_config, profile)  # 传入 profile
```

#### 修复 C: 修复 score_range 默认值
```python
# AddressSelector.__init__
self._score_range = self.profile.get("score_range") or self.profile.get("value_range", (1, 100000))
```

### 3.2 工作流改进（Next Scan 过滤层，预计 1 天）

#### 改进 A: 引入自动 Next Scan 机制
```python
# workflow_engine.py _step_select_addresses
# 未知初值扫描后，自动执行 2-3 轮轮询式 Next Scan:

# 轮 1: 等待 5 秒，扫描 Changed Value（过滤未变化的地址）
# 轮 2: 等待 5 秒，扫描 Changed Value（进一步过滤）
# 轮 3: 若地址仍 > 1000，扫描 Unchanged Value（找稳定变化的）或范围限制
```

#### 改进 B: 地址区域过滤
```python
# 在 scan_results 中排除以下区域：
# - PE 头（区域 Protection = PAGE_READONLY，且 BaseAddress 对齐 0x10000）
# - 代码段（Protection = PAGE_EXECUTE_READ）
# - 优先选择：堆（PAGE_READWRITE）、BSS/Data 段
# 使用 VirtualQueryEx 获取区域属性
```

#### 改进 C: 引入随机采样（大数据集时）
```python
# 当 scan_results > 10000 时，按区域分布均匀采样，而非取前 100
# 优先采样：堆区域、栈区域、数据段
```

### 3.3 架构升级（采集层，预计 2-3 天）

#### 升级 A: 模块级内存区域感知
```python
# 使用 EnumProcessModules + GetModuleInformation 获取模块列表
# 标记各区域类型：
#   - .text → code
#   - .data/.rdata → data
#   - .bss → uninitialized data
#   - heap → 动态分配
# AddressSelector 按区域类型加权评分
```

#### 升级 B: 引入 Guard Page / Polling 自动降级策略（已部分实现）
```python
# 当前已有：硬件断点 → guard_page → polling
# 需增加：polling 频率自适应（有变化时加速，无变化时减速）
# 增加：变化检测窗口（如 10 秒内无任何变化，提示用户操作目标程序）
```

#### 升级 C: DFG 构建从断点 trace 出发
```python
# 当断点命中时：
# 1. 使用 Zydis 反汇编当前指令（IP）
# 2. 提取指令的读/写地址和操作数
# 3. 构建 def-use chain: 哪个指令写入了目标地址？哪个指令读取了它？
# 4. 累积 10+ 次命中后，构建局部 DFG
```

### 3.4 AI 分析改进（零数据拒绝层，预计 0.5 天）

#### 改进 A: 硬性约束 prompt
```python
# ai_assistant.py reverse_engineering_assist
# 在 system prompt 中增加：
constraint = """
硬性约束：
1. 如果 total_hits == 0 且 total_nodes == 0，直接返回 "数据不足，无法分析"。
2. 禁止编造任何伪代码、算法推测或领域假设。
3. 禁止提及与进程类型无关的技术（如 HipsDaemon 与音频处理）。
4. 仅在提供具体断点记录、DFG 节点或数值变化序列时，方可进行分析。
"""
```

#### 改进 B: 数据质量评分
```python
# 在调用 AI 前，计算数据质量分数：
quality_score = min(1.0, total_hits / 10) * min(1.0, total_nodes / 5)
if quality_score < 0.3:
    return "采集数据不足（质量分 {:.1f}），建议：\n1. 在目标程序中执行操作以触发数值变化\n2. 检查断点是否正常工作".format(quality_score)
```

### 3.5 进程类型推断增强（长期，1-2 周）

#### 增强 A: 引入 YARA 风格静态签名
```python
# 预定义进程行为签名：
SIGNATURES = {
    "security_hips": {
        "process_name": ["hips", "defender", "av"],
        "api_hooks": ["NtCreateFile", "NtSetValueKey", "NtConnectPort"],  # 需额外采集
        "memory_patterns": ["policy", "rule", "threat"],  # 字符串扫描
    }
}
```

#### 增强 B: 动态行为特征
```python
# 在附加进程后，短时间内采集：
# - 文件操作频率（API hook / ETW）
# - 网络连接数
# - 线程数变化
# - 注册表操作频率
# 用这些特征辅助类型推断（类似 AMAL 的 MaLabel）
```

#### 增强 C: 网络搜索补充（用户建议）
```python
# 当本地知识库匹配度低时，自动搜索：
# "<process_name> 是什么软件" 或 "<process_name> 功能"
# 解析搜索结果补充到知识库（需联网 + NLP 摘要）
```

---

## 4. 针对 HipsDaemon 的具体分析策略

基于调研，HipsDaemon 作为安全软件应关注：

| 特征类型 | 目标数值 | 内存区域 | 变化触发方式 |
|---------|---------|---------|------------|
| 监控计数器 | 文件扫描数、注册表访问数 | 全局数据段 | 打开文件/修改注册表 |
| 威胁状态 | 威胁等级、隔离计数 | 配置数据区 | 检测到威胁 |
| 策略标志 | 策略启用/禁用（0/1） | 堆/数据段 | 用户切换策略 |
| 句柄计数 | 打开的句柄数 | 进程信息 | 监控对象变化 |

**建议测试流程**：
1. 附加 HipsDaemon → 类型推断为 `security`
2. 执行 `first_scan_unknown` → 得到 ~10^8 地址
3. 等待 10 秒，执行 `next_scan_changed` → 过滤到 ~10^4 地址
4. 再等待 10 秒，执行 `next_scan_changed` → 过滤到 ~10^2 地址
5. 在火绒界面中：切换防护状态（开→关→开），执行 `next_scan_changed` → 应找到策略标志地址
6. 对最终地址设置轮询（Polling），观察数值变化
7. 若找到变化地址，设置断点追踪写入指令 → 构建 DFG
8. AI 分析时提供具体变化记录（如 "0x7FF... 从 1 变为 0，与策略切换时间吻合"）

---

## 5. 优先级排序

| 优先级 | 任务 | 预计时间 | 影响 |
|-------|------|---------|------|
| P0 | 修复键名不匹配（cat/type, value_range/score_range） | 30 min | 解决类型推断显示问题 |
| P0 | 修复 AddressSelector 未接收 profile | 30 min | 恢复类型感知评分 |
| P1 | 引入自动 Next Scan 过滤 | 1 day | 解决地址选择无效问题 |
| P1 | 区域过滤（排除 PE 头/代码段） | 4 hours | 提高地址质量 |
| P1 | AI 零数据硬性拒绝 | 2 hours | 消除幻觉 |
| P2 | DFG 从断点 trace 构建 | 2-3 days | 提供真实分析数据 |
| P2 | Polling 自适应频率 | 4 hours | 提高采集效率 |
| P3 | YARA 风格静态签名 | 1 week | 增强类型推断 |
| P3 | 动态行为特征采集 | 1-2 weeks | 达到 AMAL 级别的自动化 |

---

*报告由 MemoryGraph 系统自动生成，基于调研论文与工具分析。*
