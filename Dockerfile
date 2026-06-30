# MemoryGraph — Discourse Block Tree
# 多阶段构建，最小化最终镜像体积

# ── 阶段 1: 构建依赖 ─────────────────────────────────────────────
FROM python:3.10-slim AS builder

WORKDIR /build

# 安装系统依赖（构建 PyTorch 等需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── 阶段 2: 运行环境 ─────────────────────────────────────────────
FROM python:3.10-slim AS runtime

WORKDIR /app

# 从构建阶段复制 Python 包
COPY --from=builder /root/.local /root/.local

# 确保本地包在 PATH 中
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8

# 复制项目代码
COPY core/ ./core/
COPY scripts/ ./scripts/
COPY README.md .

# 创建配置目录
RUN mkdir -p /root/.config/memorygraph

# 下载模型（构建时缓存）
RUN python scripts/download_models.py --bge-only || true

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python core/agent/health_check.py || exit 1

# 预启动命令（预加载模型，消除冷启动）
RUN python -c "
from core.agent.config.logging_setup import setup_logging;
from core.agent.discourse_integration import DiscoursePipeline;
setup_logging(level='INFO');
dp = DiscoursePipeline();
dp.preload(blocking=True);
print('Preload completed')
"

# 默认入口：可覆盖为具体服务
CMD ["python", "-c", "from core.agent.config.logging_setup import setup_logging; setup_logging(); print('MemoryGraph Discourse Block Tree ready')"]
