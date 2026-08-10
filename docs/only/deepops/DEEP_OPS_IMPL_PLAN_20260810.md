# 深度操作工具链 — 施工方案（2026-08-10）

> 承接: `DEEP_OPS_DESIGN_20260810.md`（设计 v3，五层策略 + 前身资产 + CLI-Anything）
> 前置决策（已拍板）:
>   - 不做独立项目，作为 DialogMesh 工具族 (ToolRegistry 注册)
>   - 反汇编是兜底不是默认（五层策略按成本优先）
>   - CLI-Anything = "CLI 即运维控制"（外部软件操作层）
>   - 轻量逆向层直接移植 DialogMesh；重量逆向层先在 MemoryGraph_old 验证再移植
> 状态: 施工方案定稿，待开工。

---

## 一、施工总览（阶段顺序）

```
阶段 A: 轻量逆向层移植 (ghidra/frida bridge — 纯 stdlib, 零依赖)
阶段 B: repomix + CLI-Anything (策略 0/1 — 最高优先, 80% 场景)
阶段 C: UI 自动化 (page-agent / UI-TARS — 策略 2)
阶段 D: 重量逆向层验证 (angr / mg_engine.dll / Zydis — 策略 3/4 重件)
阶段 E: 工具族接入蓝图 (注册 + tool 节点 + 层间降级编排)
阶段 F: CLI 控制层 RPC 化 (未来, 触发式)
```

---

## 二、阶段 A：轻量逆向层移植（今天可做）

### A.1 移植清单

| 源 (MemoryGraph_old) | 目标 (DialogMesh) | 依赖 | 行数 |
|---------------------|------------------|------|:---:|
| `core/ghidra_bridge.py` | `core/agent/tools/reverse/ghidra_bridge.py` | 纯 stdlib ✅ | 1597 |
| `core/frida_bridge.py` | `core/agent/tools/reverse/frida_bridge.py` | 纯 stdlib ✅ | 356 |
| `core/capstone_disasm.py` | `core/agent/tools/reverse/capstone_disasm.py` | capstone (pip) | 397 |
| `disasm/engine.py` | `core/agent/tools/reverse/disasm_engine.py` | capstone (pip) | 425 |
| `disasm/code_scanner.py` | `core/agent/tools/reverse/code_scanner.py` | ctypes (Win) | 569 |
| `disasm/depgraph.py` | `core/agent/tools/reverse/depgraph.py` | 纯 stdlib | 534 |
| `disasm/utils.py` | `core/agent/tools/reverse/disasm_utils.py` | 纯 stdlib | 324 |

### A.2 移植步骤

```
1. 创建 core/agent/tools/reverse/ 包 (+ __init__.py)
2. 拷贝 7 个文件 (只搬工具层, 不搬业务层)
3. 修正 import: 相对路径 → core.agent.tools.reverse.*
   (源文件里 from core.xxx → from core.agent.tools.reverse.xxx)
4. pip install capstone (唯一 Python 依赖)
5. 确认 ghidra zip 位置: ghidra/ghidra_12.1.2.zip (572MB) — 解压路径配置化
6. 写适配层: reverse/adapters.py — 把 bridge 输出转 ToolResult

验收 (A):
  [ ] import 探针: 7 文件全部可导入, 0 断链
  [ ] disasm_engine 反汇编测试: b'\x48\x89\xE5' → mov rbp, rsp
  [ ] ghidra_bridge._find_ghidra_home 找到 ghidra_12.1.2_PUBLIC
  [ ] pytest: core/agent/tools/tests/test_reverse_basic.py (新增 5+ 项)
```

---

## 三、阶段 B：repomix + CLI-Anything（策略 0/1，最高优先）

### B.1 repomix（源码打包）

```
安装: npm install -g repomix 或 npx repomix
验证: repomix pack <repo> → 单个 AI 友好文件
工具注册:
  repo_scan: 打包仓库 → LLM 理解 → 提取操作入口 (entry points/CLI/API)

验收 (B1):
  [ ] repomix pack DialogMesh → 输出单个文件
  [ ] LLM 从打包文件提取: 入口命令/关键模块/数据流
  [ ] repo_scan 工具注册 + discover("扫源码") 命中
```

### B.2 CLI-Anything（软件 → CLI 包装）

```
来源: HKUDS/CLI-Anything (⭐46.8K, Apache-2.0, 港大)
理念: Making ALL Software Agent-Native / CLI-Hub (clianything.cc)
安装: git clone + pip install (按官方 README)
验证: 对一个目标软件自动生成 Python CLI
工具注册:
  cli_gen: 软件 → 自动 CLI 包装 → agent 控制
  演进: 常用控制路径 → RPC 化 (阶段 F)

验收 (B2):
  [ ] CLI-Anything 安装成功
  [ ] 对一个开源工具生成 CLI 包装成功
  [ ] 生成的 CLI 可被 DialogMesh 调用 (subprocess)
  [ ] cli_gen 工具注册 + discover("生成CLI") 命中
```

---

## 四、阶段 C：UI 自动化（策略 2）

### C.1 page-agent（DOM，web 优先 — 你们前端是 React）

```
来源: alibaba/page-agent (⭐28.5K)
方式: JS 注入页面 → 直接操控 DOM → 自然语言指令
验证: 对 frontend/ 起的 vite dev server 做 UI 测试

工具注册:
  ui_test (DOM 模式): 点击/输入/断言 → page-agent
```

### C.2 UI-TARS（视觉，通用兜底）

```
来源: bytedance/UI-TARS (⭐11.3K, Apache-2.0) + UI-TARS-desktop (⭐38.5K)
轻量验证: pip install ui-tars → parse_action_to_structure_output
  (只测解析器, 不跑视觉模型 — 验证链路)
完整验证: 视觉模型 (qwen25vl) → 截图 → 动作序列

工具注册:
  ui_test (视觉模式): 截图 → UI-TARS → pyautogui 执行
```

### C.3 工具合并策略

```
ui_test 一个工具, 两种模式 (参数切换):
  mode="dom"  → page-agent (快, web)
  mode="vision" → UI-TARS (通用, 慢)
  → discover 按关键词命中后, 蓝图选模式 (A7 信息论分治)

验收 (C):
  [ ] pip install ui-tars 成功, 解析器测试通过
  [ ] page-agent 对 DialogMesh 前端跑通一个 UI 用例
  [ ] ui_test 工具注册 (双模式) + 蓝图 tool 节点
  [ ] 层间降级: ui_test 失败 → 提示降级 hook_probe
```

---

## 五、阶段 D：重量逆向层验证（先在 MemoryGraph_old 验证再移植）

### D.1 验证清单（在 MemoryGraph_old 环境）

```
1. angr_bridge (847 行) — 符号执行
   → 装 angr (~500MB), 跑通符号执行路径探索
   → 验证: 简单二进制 → 约束求解 → 目标地址可达
2. mg_engine.dll (84KB) + tracer_v2 (327 行) — 断点引擎
   → 确认 C++ 源码完整 (ScannerEngine.cpp 155 行? 搜其他 .cpp)
   → 验证: dll 加载 + int3 断点 + 执行流捕获
3. Zydis (analysis/zydis_engine.py 929 行) — 近源码反汇编
   → build_zydis.bat 编译验证 (zydis 是 C 库, 需构建)
4. deobfuscator/junk_code/anti_debug/dfg (1665 行) — 加固对抗
   → 逐文件 import 探针 + 单测

### D.2 移植条件（全部验证通过才移植）

```
移植到 DialogMesh 的触发条件:
  [ ] angr_bridge 符号执行跑通
  [ ] mg_engine.dll 加载 + 断点工作
  [ ] Zydis 编译成功
  [ ] 加固对抗 4 文件 import 探针通过
→ 任一失败: 记录缺口, 该模块留在 MemoryGraph_old, 不阻塞其他阶段
```

---

## 六、阶段 E：工具族接入蓝图（整合）

### E.1 工具注册总表（9 个）

| 工具 | 策略 | 来源 | 风险 |
|------|:---:|------|:---:|
| `repo_scan` | 0 | repomix | 低 |
| `cli_gen` | 1 | CLI-Anything | 低 |
| `ui_test` | 2 | page-agent / UI-TARS | 中 |
| `hook_probe` | 3 | frida_bridge (前身) | 中 |
| `net_trace` | 3.5 | mitmproxy (新补) | 中 |
| `disasm_lib` | 4 | ghidra_bridge (前身) | 高 |
| `xref` | 4 | code_scanner (前身) | 高 |
| `dataflow` | 4 | depgraph (前身) | 高 |
| `sym_exec` | 4 | angr_bridge (前身) | 高 |

### E.2 蓝图集成

```
1. ToolRegistry.register × 9 (builtin.py 或 reverse_tools.py)
2. 蓝图 tool 节点: T2 校验 / T3 回灌 / T4 ReAct (已有机制, 复用)
3. 层间降级编排 (设计 §2.3):
   "操作 X" → repo_scan? → cli_gen? → ui_test? → hook? → 逆向?
   → 实现为蓝图模板: ops_flow 种子模板
4. 安全: risk=high 工具 → PlanGate 显式确认 (已有)
   目标白名单: hook_probe 需要目标进程名白名单
5. 行为闭环: 操作历史 → 行为链学习 (A9) → 下次更快

### E.3 验收 (E)

```
  [ ] 9 工具全部注册, discover 中英关键词命中
  [ ] 蓝图 ops_flow 模板: 从"操作 X"到"结果回灌"端到端
  [ ] PlanGate 对 disasm_lib/sym_exec 生效
  [ ] 行为链记录操作历史 (验证白盒 A19)
  [ ] 全量 pytest 回归无破坏
```

---

## 七、安全边界（A21 不可协商）

```
默认: 策略 0-3 (repo_scan/cli_gen/ui_test/hook_probe/net_trace) — 无显式确认
高风控: 策略 4 (disasm_lib/xref/dataflow/sym_exec) — PlanGate 显式确认
技术护栏:
  hook_probe: 目标进程白名单 (默认仅 DialogMesh 自己的进程)
  net_trace: 仅回环 + 用户指定目标
  策略 4 工具: 操作记录 + 用途声明 (调试/定制, 非绕过授权)
用户已确认: 技术本身合理 (类 nmap), 单用户 + 显式操作 + PlanGate 风险可控
```

---

## 八、阶段 F：CLI 控制层 RPC 化（未来，触发式）

```
触发条件: 常用控制路径稳定后 (cli_gen 生成的 CLI 被频繁调用)
实现: 常用操作 → RPC 调用 (长连接/批量/结构化)
  与 B4-5 同一哲学: CLI 轻量起步, RPC 高效升级
  可复用: service/protocol/ (B4-1 保留的协议资产)
验收: 常用控制延迟 ↓ 或吞吐 ↑, 前端/多 agent 直连可用
```

---

## 九、施工顺序建议（执行计划）

```
第 1 步 (今天): 阶段 A — 轻量逆向层移植 (7 文件, ~2h)
   ├─ 建 reverse/ 包 + 拷贝 + import 修正
   ├─ pip install capstone
   └─ 验收 A (import 探针 + 反汇编测试)

第 2 步 (今天): 阶段 B — repomix + CLI-Anything 安装验证 (~1h)
   ├─ npx repomix pack 验证
   ├─ CLI-Anything clone + install
   └─ 验收 B1/B2

第 3 步: 阶段 C — UI 自动化 (~2h)
   ├─ pip install ui-tars (轻量解析器)
   ├─ page-agent 对 frontend 跑通一个用例
   └─ 验收 C

第 4 步: 阶段 E — 工具族接入蓝图 (~2h)
   ├─ 9 工具注册 + discover 验证
   ├─ ops_flow 种子模板
   └─ 验收 E

第 5 步 (并行/后台): 阶段 D — 重量逆向层验证
   ├─ angr 安装 (大, 后台)
   ├─ mg_engine.dll C++ 源码确认
   └─ 按验证结果决定移植

第 6 步 (未来): 阶段 F — RPC 化 (触发式)
```

---

## 十、风险与回退

```
风险 1: ghidra 12.1.2 解压/运行问题 (Windows)
  → 回退: 用 ghidra_bridge 的 headless 模式配置检查, 先注册后验证
风险 2: angr 安装失败 (依赖冲突)
  → 回退: sym_exec 标记"待环境", 不阻塞其他工具
风险 3: mg_engine.dll C++ 源码不完整 (ScannerEngine.cpp 仅 155 行?)
  → 回退: 断点追踪用 frida 替代 (frida_bridge 已有栈追踪)
风险 4: CLI-Anything 与项目架构不兼容
  → 回退: 手动包装常用 CLI (少量), 不依赖自动生成
风险 5: 移植文件 import 断链
  → 回退: 逐文件 import 探针, 修正相对导入

每个阶段独立验收, 任一失败不阻塞其他阶段 (模块化施工)
```
