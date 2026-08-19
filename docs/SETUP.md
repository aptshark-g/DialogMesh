# DialogMesh 依赖清单与一键安装（2026-08-19）

> 目标: 让 GitHub 用户 clone 后能一次跑起来。
> 一键安装: `python scripts/setup_env.py`（Windows/Linux/macOS 通用, 仅标准库）。

## 依赖清单表

| # | 依赖 | 版本要求 | 来源 | 安装方式 | 一键 |
|---|------|---------|------|---------|------|
| 1 | Python | 3.10 – 3.13 | [python.org](https://www.python.org/downloads/) | 手动安装 | `setup` 检查 |
| 2 | Node.js + npm | ≥ 18 | [nodejs.org](https://nodejs.org/) | 手动安装 | `setup` 检查 |
| 3 | Python 依赖 | `requirements.txt`（numpy/torch/fastapi…） | PyPI | `setup` 自动 `pip install` | ✅ |
| 4 | 前端依赖 + 构建 | `frontend/package.json` | npm | `setup` 自动 `npm install && npm run build` | ✅ |
| 5 | switch 网关二进制 | `gateway/gateway.exe`（或 `gateway` 目录下同名） | GitHub release / Go 源码构建 | `setup` 自动下载或 `go build` | ✅ |
| 6 | `gateway/provider.yaml` | —（含密钥, 不入库） | 仓库示例 `provider.example.yaml` | `setup` 自动复制 | ✅ |
| 7 | `.env` | —（本地配置, 不入库） | 仓库示例 `.env.example` | `setup` 自动复制 | ✅ |
| 8 | 嵌入模型 BGE-small-zh | ~13 MB | ModelScope | 运行时自动下载 / `setup --models` 预下载 | 可选 |
| 9 | BGE-M3（增强召回, 可选） | ~2.3 GB | ModelScope | 运行时按需（`DM_BGE_M3=1`） | 可选 |
| 10 | Rust 持久化/召回内核（可选） | `persistence_rs` / `recall_rs` | 仓库源码 | 手动 `cargo build --release`（未来默认启用） | 可选 |

## 一键安装

```bash
# 1. 克隆
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh

# 2. 一键检查 + 安装环境（Python 依赖较大会花几分钟~十几分钟）
python scripts/setup_env.py

# 3. 启动（Windows）
start.bat
# 或手动:
python scripts/start_server.py
```

## 手动安装（不想用一键脚本）

```bash
# Python 依赖
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/python -m pip install -r requirements.txt       # Linux/macOS

# 前端
cd frontend && npm install && npm run build && cd ..

# 配置
cp .env.example .env
cp gateway/provider.example.yaml gateway/provider.yaml     # 填入你的 API Key

# 网关二进制（二选一）:
#   A) 有 Go: git clone https://github.com/aptshark-g/switch.git && cd switch && go build -o ../DialogMesh/gateway/gateway.exe cmd/gateway
#   B) 下载已发布 release（见 README 或 setup 脚本输出）
```

## 验证

- 网关: http://localhost:8080（`/v1/health` 返回 ok）
- API: http://localhost:8000/docs
- 前端: http://localhost:4173

> 首次启动会按需自动下载嵌入模型（BGE-small-zh, 13MB）; 断网时以离线优先
> 模式运行（模型需已缓存）。若需更高质量的语义召回, 设置 `DM_BGE_M3=1`
> 启用 BGE-M3（首次自动下载 ~2.3GB）。
