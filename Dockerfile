# ═══════════════════════════════════════════════════════════════════════════════
# DialogMesh — Multi-stage Dockerfile (Phase 5)
# ═══════════════════════════════════════════════════════════════════════════════
#  Base: docker.mirrors.ustc.edu.cn/library/python:3.11-slim
#  Target: ~700–900 MB (PyTorch is the main contributor; best-effort < 500 MB)
#  Non-root user | Multi-stage | Health checks | BGE model cache
# ───────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies (gcc, g++ for compiling sentencepiece, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment for clean isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency manifests first (for layer caching)
COPY requirements.txt pyproject.toml README.md ./

# Install third-party dependencies (no project source needed)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code needed for editable install & model cache warm-up
COPY core/       ./core/
COPY scripts/    ./scripts/

# Install DialogMesh in editable mode (needs core/ for setuptools find)
RUN pip install --no-cache-dir -e ".[service,metrics,config]"

# Generate BGE embedding model cache (build-time download)
# Falls back to huggingface transformers if ModelScope CLI fails
RUN python scripts/download_models.py --bge-only || echo "Model cache step skipped (will download at runtime)"

# ── Stage 2: Runtime ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="DialogMesh Contributors" \
      org.opencontainers.image.title="DialogMesh" \
      org.opencontainers.image.description="Industrial-grade dialogue context management microservice" \
      org.opencontainers.image.version="2.4.0"

WORKDIR /app

# Environment
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PATH="/opt/venv/bin:$PATH"

# Runtime system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder (all Python packages)
COPY --from=builder /opt/venv /opt/venv

# Copy cached models from builder (if generated)
COPY --from=builder /build/models ./models

# Copy application code
COPY requirements.txt pyproject.toml README.md ./
COPY config/     ./config/
COPY core/       ./core/
COPY service/    ./service/
COPY gui/        ./gui/
COPY data/       ./data/
COPY deploy/     ./deploy/
COPY scripts/    ./scripts/
COPY tests/      ./tests/

# Ensure runtime directories exist and are writable
RUN mkdir -p /app/data /app/logs /app/uploads && \
    chmod -R 755 /app/data /app/logs /app/uploads

# Create non-root user & group
RUN groupadd -r dialogmesh && \
    useradd -r -g dialogmesh -d /app -s /sbin/nologin dialogmesh && \
    chown -R dialogmesh:dialogmesh /app

# Switch to non-root user
USER dialogmesh

# Expose FastAPI (8000) and optional Nginx upstream (8080)
EXPOSE 8000 8080

# Health check against root /health endpoint (no /v1/ prefix)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI application via factory mode
CMD ["uvicorn", "service.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
