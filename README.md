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

# 配置 DeepSeek API Key
# 编辑 gateway/provider.yaml → deepseek.api_key: sk-xxx

# 一键启动 (Gateway + API + Frontend)
python scripts/start.py
```

- Gateway: http://localhost:8080 (LLM 代理)
- API: http://localhost:8000/docs (90 端点)
- GUI: http://localhost:4173 (前端)

---

## 架构

```
                      ┌──────────────────────┐
                      │   switch Gateway     │
                      │   断路器 · 限流 · 缓存 │
                      └──────┬───────────────┘
                             │
  ┌──────────┬──────────┬────┴─────┬──────────┬──────────┐
  │ 对话树   │ 行为链   │ 关联链   │ 工程链   │ 画像     │
  │ 01-04    │ 05       │ 06       │ 07       │ 08       │
  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┘
       │          │          │          │          │
       └──────────┴──────────┴──────────┴──────────┘
                            │
              ┌─────────────┴─────────────┐
              │  子图编译器 (链 10)       │
              │  元认知第二大脑 (链 09)    │
              └───────────────────────────┘
```

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 🧠 **10 条业务链** | 对话树 + 行为预测 + 关联漏斗 + 工程约束 + 画像惯性 + 元认知 + 子图 |
| 🎯 **全局状态机** | Event Sourcing + Decider + ShardedState, 防广播风暴 |
| 🔗 **关联链五层漏斗** | L1句法 → L1.5补全 → L2语义 → L2.5信念 → L3意图 → L4时序 → L5因果 |
| 👤 **画像 v2** | 惯性权重图 + 多视角共识 + OCEAN 10维 + BFI-10 校准 |
| 🛡️ **Git 版本控制** | 8类数据不可变日志, SHA256链, 回滚, 审计 |
| 📊 **90 端点** | REST API 全覆盖, 含元认知/版本/惯性/行为/因果/调度器 |
| 🔄 **4 路径调度** | Fast(<50ms) → Async(LLM) → Slow(Checkpoint) → Deep(复盘) |
| ⚡ **switch Gateway** | 滑动窗口断路器 + Gradient2自适应 + 加权路由 + 请求合并 |

---

## 快速命令

```bash
# A/B 画像测试
.venv-test\Scripts\python core\agent\v4\cognitive\tests\bench_ab_ocean.py

# 一键启动 (含 Gateway)
python scripts\start.py

# 仅 DialogMesh (无 Gateway)
python scripts\start.py --no-switch
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
