# God-Kaiser Server - Dockerfile
# ===============================
# Multi-stage build for FastAPI backend
#
# Build: docker build -t el-servador .
# Run:   docker run -p 8000:8000 el-servador

# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VERSION=1.7.1
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Copy dependency files
COPY god_kaiser_server/pyproject.toml god_kaiser_server/poetry.lock* ./

# Configure Poetry: no virtual env, install only main deps
# --no-root: Don't install the project package itself (only dependencies)
# This avoids errors about missing README.md in the Docker build context
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main --no-root && \
    pip install "pyserial>=3.5,<4.0" && \
    pip install "esp-idf-nvs-partition-gen>=0.2.0" && \
    pip install "esptool>=4.0"

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# Install runtime dependencies and apply security patches
# postgresql-client-16 from PGDG repo — must match postgres:16-alpine (Fix-T Block 1)
# Default Bookworm postgresql-client is v15, which refuses to pg_dump a v16 server
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    gnupg \
    && echo "deb http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/pgdg.gpg \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Upgrade pip/setuptools and fix known CVEs in transitive/lock-pinned packages:
# python-multipart CVE-2024-24762, CVE-2024-53981, CVE-2026-24486 → >=0.0.22
# starlette CVE-2024-47874 → >=0.40.0 (via FastAPI >=0.115.0)
# jaraco.context CVE-2026-23949 (path traversal) → >=6.1.0
# wheel CVE-2026-24049 (privilege escalation) → >=0.46.2
RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir --upgrade \
        "python-multipart>=0.0.22" \
        "fastapi==0.133.0" \
        "starlette>=0.40.0,<1.0.0" \
        "jaraco.context>=6.1.0" \
        "wheel>=0.46.2"

# Copy application code
COPY god_kaiser_server/src ./src
COPY god_kaiser_server/alembic ./alembic
COPY god_kaiser_server/alembic.ini ./alembic.ini

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/logs /app/backups/database && \
    chown -R appuser:appuser /app

USER appuser

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

# Run with uvicorn (--no-access-log: custom RequestIdMiddleware logs requests with CID)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
