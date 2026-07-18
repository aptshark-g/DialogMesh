# DialogMesh v6 CLI 命令大全

## 基础用法

```bash
.venv-test\Scripts\python core\agent\v4\cli.py <命令> [选项]

# 或 (Windows)
set PYTHONHOME= & set PYTHONPATH=
.venv-test\Scripts\python core\agent\v4\cli.py <命令> [选项]
```

---

## 命令列表 (8个)

### 1. chat — 交互对话

启动交互式对话会话，系统全程跟踪并分析用户人格特征。

```bash
cli.py chat [--turns N]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--turns N` | 对话轮数 | 10 |

**产出文件**:
| 文件 | 说明 |
|------|------|
| `data/monitor/chat_<ts>.jsonl` | 每轮全量快照 (trace/OCEAN/BFI/TrackB) |
| `data/monitor/chat_<ts>_profile.json` | TrackB 标签快照 |
| `data/monitor/chat_<ts>_summary.json` | 最终分析摘要 |
| `data/profile/ocean_profile.json` | 跨会话 OCEAN 画像 |
| `data/neuro_symbolic_rules.json` | 学习到的规则 |
| `data/mind_*.json` | Mind 关系/锚点/错误模式 |

**示例**:
```bash
cli.py chat              # 10轮对话
cli.py chat --turns 20   # 20轮对话
```

---

### 2. test — 运行基准测试

```bash
cli.py test [bench]
```

| bench | 轮数 | 说明 |
|-------|------|------|
| `all` | 全量 | live + controlled + implicit + monitored |
| `live` | 22 | 4场景 (Persona/MultiHop/TopicSwitch) |
| `controlled` | ~16 | 4对照实验 (Mind/REJECT/Personality/Fork) |
| `implicit` | 10 | T/F 风格暗提取测试 |
| `monitored` | 10 | 全量监控测试 |

**示例**:
```bash
cli.py test all          # 全量基准 (~50轮, 约30分钟)
cli.py test live         # 仅 live benchmark
cli.py test implicit     # 仅暗提取测试
```

---

### 3. ab — A/B 对比测试

重放上一轮对话，对比 CoT+BFI 修复前后的 OCEAN 维度差异。

```bash
cli.py ab
```

**产出**: 终端输出 PREV vs AFTER 对比表

**示例**:
```bash
cli.py ab
# 输出:
#   PREV:  INTP  C=0.46 A=0.41
#   AFTER: ENTJ  C=0.78 A=0.46
#   Diff:  C: +0.32 ✅ J detected
```

---

### 4. profile — 查看/重置画像

```bash
cli.py profile [--reset]
```

| 选项 | 说明 |
|------|------|
| (无) | 显示当前 OCEAN 10维画像 + MBTI |
| `--reset` | 清除画像，下次从零开始 |

**示例**:
```bash
cli.py profile           # 查看画像
# OCEAN Profile — 10 turns — MBTI≈ENTJ
#   C: 0.78 ███████░░░
#   O: 0.68 ██████░░░░
#   E: 0.59 █████░░░░░

cli.py profile --reset   # 重置画像
```

---

### 5. monitor — 查看会话日志

```bash
cli.py monitor [--list]
```

| 选项 | 说明 |
|------|------|
| (无) | 显示最近会话的末尾5轮 |
| `--list` | 列出所有会话文件及大小 |

**示例**:
```bash
cli.py monitor                     # 最新会话
# Latest: chat_1784366450.jsonl — 10 turns
#   T8: S=0 W=0 ocean=ENTJ

cli.py monitor --list              # 所有会话
#   chat_1784366450.jsonl  (6042B)
#   chat_1784365004.jsonl  (6087B)
```

---

### 6. export — 导出数据

```bash
cli.py export [--format json|csv] [--output PATH]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--format` | 导出格式 | `json` |
| `--output` | 输出文件路径 | `export.json` / `export.csv` |

**示例**:
```bash
cli.py export                           # JSON → export.json
cli.py export --format csv --output ocean.csv  # CSV
```

---

### 7. config — 查看配置

```bash
cli.py config
```

显示当前持久化状态、Python路径、工作目录。

**示例**:
```bash
cli.py config
# DialogMesh v6 Configuration
#   OCEAN profile: True
#   ABC rules: True
#   Mind relations: False
#   Monitor sessions: 40
```

---

### 8. clean — 重置数据

```bash
cli.py clean [--all]
```

| 选项 | 说明 |
|------|------|
| (无) | 重置画像/规则/Mind |
| `--all` | 同时清除监控日志和标注 |

**示例**:
```bash
cli.py clean             # 重置核心数据
cli.py clean --all       # 完全重置
```

---

## 典型工作流

```bash
# 1. 对话并建立画像
cli.py chat --turns 10

# 2. 查看画像
cli.py profile

# 3. 再次对话 (自动加载上一轮画像)
cli.py chat --turns 10

# 4. 对比修复效果
cli.py ab

# 5. 导出数据做外部分析
cli.py export --format csv

# 6. 需要时重置
cli.py clean
```

---

## 数据文件位置

```
data/
├── profile/
│   └── ocean_profile.json          # 跨会话 OCEAN 画像
├── monitor/
│   ├── chat_<ts>.jsonl             # 每轮全量快照
│   ├── chat_<ts>_profile.json      # TrackB 标签
│   └── chat_<ts>_summary.json      # 最终摘要
├── annotations/                    # 统一标注存储
│   ├── mind/
│   ├── rules/
│   └── patterns/
├── mind_relation.json              # Mind 关系
├── mind_attention.json             # Mind 锚点
├── mind_mistakes.json              # Mind 错误模式
└── neuro_symbolic_rules.json       # ABC 规则
```
