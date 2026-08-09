# OpenClaw OS 控制工具参考 → 我们的实现设计（2026-08-08）

> 触发: 用户问"让 agent 实现软件现在能做吗" → 核查发现缺 OS 控制
> 方法: GitHub 拉 OpenClaw 核心源码精读（shell-dynamic-tools.ts +
> code-execution.md + exec/exec-approvals 文档）

---

## 一、OpenClaw 模式（源码证据）

### exec（本地 shell 执行）
- 参数: command + 策略参数（host/security/ask）
- **approval/allowlist 策略**: 命令白名单 + 审批门（= 我们的 PermissionEngine）
- 结构化错误返回（非异常）→ agent 可自纠正
- 超时控制

### node_exec / node_process（远程节点 + 会话管理）
- `node_exec`: 跑 shell（可后台）
- `node_process`: 会话生命周期 list/poll/log/write/send-keys/
  submit/paste/kill/clear/remove（长任务跟进）
- 策略: host 固定 + approval + allowlist

### code_execution（沙箱远程 Python）
- 云端沙箱（xAI 服务器）, 单次调用无状态 — 与我们本地场景无关

## 二、我们的差距（核查确认）

| 能力 | 现状 | 缺 |
|---|---|---|
| 文件读写 | ✅ file_read/file_write | — |
| 网络 | ✅ arxiv/web_fetch/pdf | — |
| 本地 shell | ❌ 无 exec 工具 | **run_shell** |
| 长任务会话 | ❌ | process 管理（v2） |
| 代码执行/测试 | ❌ | run_python（第一版可简） |
| 审批策略 | ✅ PermissionEngine（F1 已接 executor） | — |
| 文件沙箱 | ✅ FileSandbox（COW/diff） | — |

## 三、实现设计（第一版）

### T1. run_shell（本地 shell 执行）
```
注册 ToolRegistry: name=run_shell, risk=EXEC（权限引擎已分类）
参数: command(必填), timeout_s(默认30), cwd(默认工作区)
安全:
  - executor 的 PermissionEngine resolver 已拦截链式 shell（&&/|/;）+
    出根目录写（F1）
  - 超时 kill 子进程（防挂死）
  - 结构化返回 {stdout, stderr, exit_code, timed_out}
    → 失败不抛异常, agent 可自纠正（OpenClaw 同构）
```

### T2. run_python（代码执行, 第一版简化）
```
参数: code(必填), timeout_s(默认30), cwd
安全: 与 run_shell 同权限门; 输出截断防爆
用途: 测试/计算/脚本（实现软件的核心）
```

### v2（记录不施工）
- process 会话管理（后台长任务 + poll/kill）
- 远程节点（node_exec 对标, 需基础设施）
- 浏览器自动化（OpenClaw pw-tools, 用户 UI 测试已有 Playwright 基建）

## 四、验收
- `dm` 蓝图工具节点含 run_shell 时, 生产路径权限门生效
- run_shell 跑 `git status` 返回真实输出; `&& rm -rf` 被权限拦
- run_python 跑一段计算/测试脚本返回结果
- 超时命令被 kill（不挂死）

## 五、施工进度（2026-08-08）

### ✅ 已实现（os_tools.py, 11/11 测试）
- `run_shell`: 平台 shell（cmd /c / sh -c）+ 超时 kill 进程树 +
  结构化返回（stdout/stderr/exit_code/timed_out）
- `run_python`: 代码执行, 同权限门 + 输出截断（20K）
- `run_session`: 后台长任务会话 new/poll/kill/list（OpenClaw
  node_process 对标, 第一版子集）
- `dir_list`: 目录列表（查看项目结构）
- `grep`: 文件/目录递归搜索（OpenWorker 探索先行）
- 权限门: run_shell/run_python 归 EXEC 风险, 链式 shell 被拒
  （实测: `git status && rm` → rejected; 正常命令 → approved）

### 🔴 踩坑（已修）
- ToolAdapter 无 `risk`/`execute` 字段 → 用 `category`+`availability`+`handler`
- ToolResult 字段是 `tool_name/success` 非 `ok`
- Windows `echo` 是 cmd 内置 → Popen(['echo']) 失败 → cmd /c 包装
- 字符串跨行语法错误（description 用相邻字符串拼接）
- `os.walk` 不遍历单文件 → grep 文件/目录分路径

### 📌 v2（记录不施工）
- 持久 shell 会话（cd/env 持久, OpenWorker run_shell 语义）
- 远程节点执行（OpenClaw node_exec）
- 浏览器自动化工具（OpenClaw pw-tools; 我们有 Playwright 基建）
