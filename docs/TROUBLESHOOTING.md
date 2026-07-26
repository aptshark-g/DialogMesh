# DialogMesh 已知问题与解决方案

> 2026-07-25 · 重复出现的问题记录

---

## 1. 端口占用 (重复 4+ 次)

### 现象
```
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)
[WARN] Port 8080 already in use
```

### 根因
- 旧进程未正确关闭 → 端口仍被占用
- Windows 默认 TIME_WAIT=120s
- 多次启动脚本叠加

### 解决
1. `SO_REUSEADDR` — start_server.py 已加 (2026-07-25)
2. 启动前 `_check_port()` → 占用时提示而非报错
3. Gateway: 必须在 `gateway/` 目录运行 (provider.yaml 位置)

### 快速清理
```bash
# Windows
netstat -ano | findstr :8000    # 找到 PID
netstat -ano | findstr :8080    # 找到 PID
taskkill //PID <pid> //F

# Linux/Mac
lsof -i :8000 | grep LISTEN
kill -9 <pid>
```

---

## 2. Gateway: provider.yaml not found

### 现象
```
gateway: config: read provider.yaml: The system cannot find the file specified.
```

### 根因
`gateway.exe` 在当前工作目录查找 `provider.yaml`

### 解决
必须从 `gateway/` 目录或绝对路径运行：
```bash
cd gateway && ./gateway.exe
# 或
./gateway/gateway.exe  # 需要 gateway/ 下的 provider.yaml
```
start_server.py 已设置 cwd=gateway/ (2026-07-25)

---

## 3. ModuleNotFoundError: core.agent.v3_2.integration

### 现象
```
AgentPipeline lazy import failed: No module named 'core.agent.v3_2.integration'
```

### 根因
v3_2 遗留模块未移植到 v6，lazy import 失败

### 影响
仅警告，不影响功能。优雅降级已处理。

---

## 4. 模块导入链过重 (超时)

### 现象
```
[Command timed out after 5s]
```

### 根因
import chain: agent_native → UnifiedContext → DiscourseManager → v3 重依赖

### 解决
v6_app.py 绕过重依赖，独立入口。start_server.py 已切到 v6_app。

---

## 5. pydantic_core 损坏 (hermes venv)

### 现象
```
ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
```

### 影响
仅影响 hermes venv 的 python，不影响项目编译。项目用 conda python。

### 解决
```bash
pip install --force-reinstall pydantic pydantic-core
```
