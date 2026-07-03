# ═══════════════════════════════════════════════════════════════════════════════
# DialogMesh v3.0 — Multi-stage Dockerfile
# ═══════════════════════════════════════════════════════════════════════════════
#  Base: python:3.11-slim
#  Target: ~800–1000 MB (PyTorch is the main contributor)
#  Non-root user | Multi-stage | Health checks
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
COPY requirements.txt pyproject.toml ./

# Install third-party dependencies (no project source needed)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# NOTE: No `pip install -e .` needed — PYTHONPATH=/app in runtime lets Python
# discover the `core` package directly. All third-party deps are already
# installed via `requirements.txt`.

# ── Stage 2: Runtime ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="DialogMesh Contributors" \
      org.opencontainers.image.title="DialogMesh" \
      org.opencontainers.image.description="DialogMesh v3.0 — Multi-layer LLM cognitive architecture" \
      org.opencontainers.image.version="3.0.0"

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

# Copy application code
COPY requirements.txt pyproject.toml main_v3.py ./
COPY config/     ./config/
COPY core/       ./core/
COPY scripts/    ./scripts/
# NOTE: data/ is runtime-mounted via compose volume; mkdir below creates empty dir
# Do NOT COPY data/ here — local data/ may not exist and runtime uses volume mount

# Ensure runtime directories exist and are writable
RUN mkdir -p /app/data /app/logs /app/uploads && \
    chmod -R 755 /app/data /app/logs /app/uploads

# Create non-root user & group
RUN groupadd -r dialogmesh && \
    useradd -r -g dialogmesh -d /app -s /sbin/nologin dialogmesh && \
    chown -R dialogmesh:dialogmesh /app

# Switch to non-root user
USER dialogmesh

# Expose FastAPI port
EXPOSE 8000

# Health check against v3.0 /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run DialogMesh v3.0 via main_v3.py
CMD ["python", "main_v3.py", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
