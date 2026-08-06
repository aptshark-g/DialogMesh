# DialogMesh v6

[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![Phase](https://img.shields.io/badge/phase-v6%20complete-blue)](docs/INDEX.md)
[![API](https://img.shields.io/badge/API-90%20endpoints-green)](docs/GUI_API.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

> **网状认知引擎** — 10 条业务链 × 全局状态机 × Event Sourcing
>
> 对话树 + 行为链 + 关联链 + 工程链 + 元认知 + 子图编译器
>
> 白盒化：每个模块可查看、可编辑、可回溯。Git 式版本控制。

---

## 是什么

DialogMesh v6 是一个**网状认知运行时**——不是线性 RAG 管道，是多链协调的状态机：

- **对话树** (9维粘合度, 4态温度) → 上下文管理
- **行为链** (四层决策树 + ε-greedy) → 预测用户下一步
- **关联链** (五层漏斗 L1→L5) → 语义关系发现与晋升
- **工程链** (7类节点 + 约束推理) → 代码/设计约束传导
- **元认知** (审核队列 + 复盘引擎) → 系统的第二大脑
- **switch Gateway** (断路器 + 自适应并发) → 工业级 LLM 代理

[业务链索引 →](docs/INDEX.md) · [架构全貌 →](docs/ARCHITECTURE_OVERVIEW.md) · [GUI API →](docs/GUI_API.md)

---

## 一键启动

```bash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh

# 配置 switch gateway 的 provider.yaml（已预置 DeepSeek 等 9 个厂商）
# 编辑 gateway/provider.yaml → 填入 API Key

# Windows: 双击 start.bat
# 或命令行:
python scripts/start_server.py
```

- Switch Gateway: http://localhost:8080 (LLM 代理，9 厂商)
- API: http://localhost:8000/docs (44 端点)
- GUI: http://localhost:4173 (React 前端)
- 前端预览: `cd frontend && npx vite preview --port 4173`

---

## 架构

```
用户输入 → [PCR 路由] → [Intent 意图] → [Profile 画像注入] → [LLM via switch]
                │                                              │
                └── [task_graph 规划] ←────────────────────────┘
                
已接入:           ✅ PCR · Intent · Profile · LLM · 持久化
桥接空跑:         ⚠️ Behavior · Association · Meta
未接入:           ❌ Context (8,000L) · Subgraph · Engineering
```

---

## 核心能力

| 能力 | 状态 |
|------|:----:|
| 🧠 **Intent 分析** — DualTrack 意图拆分 + 路由 | ✅ |
| 👤 **用户画像** — OCEAN 5维 + MBTI + BFI-10 | ✅ |
| 📋 **任务规划** — LLM 生成 task_graph | ✅ |
| 💬 **实时对话** — DeepSeek v4 真实回复 | ✅ |
| 💾 **持久化** — JSON 文件存储，重启不丢失 | ✅ |
| 🔗 **关联链** — 五层漏斗 L1-L5 | ⚠️ |
| 🛡️ **Git 版本控制** — SHA256 链事件日志 | ✅ |
| ⚡ **switch Gateway** — 断路器 + 自适应 + 加权路由 | ✅ |

---

## 快速命令

```bash
# 启动后端 (Windows)
start.bat

# 启动后端 (Mac/Linux)
python scripts/start_server.py

# 仅 API (无 Gateway)
python scripts/start_server.py --no-gateway

# 启动前端开发服务器
cd frontend && npm run dev

# 构建前端
cd frontend && npx vite build && npx vite preview --port 4173
```

---

## 文档导航

| 文档 | 内容 |
|------|------|
| [业务链索引](docs/INDEX.md) | 10 链 + 交叉引用矩阵 |
| [架构全貌](docs/ARCHITECTURE_OVERVIEW.md) | 全局状态机 × Event Sourcing |
| [系统调度器](docs/DESIGN_SYSTEM_SCHEDULER.md) | WAL + CRDT + 因果锚点 |
| [全局状态机](docs/DESIGN_GLOBAL_STATE_MACHINE.md) | Command→Event→State 三阶段 |
| [GUI API v10](docs/GUI_API.md) | 90 端点完整文档 |
| [网关设计](switch/docs/BUSINESS_CHAIN_01_GATEWAY.md) | switch Gateway 工业级设计 |
| [网关业务流](switch/docs/BUSINESS_FLOW_GATEWAY.md) | 管理员+用户+监控三主线 |
| [实现现状](docs/IMPLEMENTATION_REALITY.md) | 代码 vs 设计 覆盖率 |
| [P0 审计](docs/P0_AUDIT.md) | P0 10/10 完成质量 |
| [完备性审计](docs/COMPLETENESS_AUDIT.md) | 10/10 链闭环状态 |
