# =============================================================================
# Platform God - Multi-Stage Production Dockerfile
# =============================================================================
# Builds a minimal, secure container image for running Platform God
# Supports both CLI commands and API server mode
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS builder

# Set build arguments
ARG PYTHON_VERSION=3.14
ARG PGOD_VERSION=0.1.0

# Set environment for build
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies (required for compiling some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libc-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /build

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv if available, otherwise pip
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    if command -v uv >/dev/null 2>&1; then \
        pip install uv && \
        uv pip install --system -e .; \
    else \
        pip install -e .; \
    fi


# -----------------------------------------------------------------------------
# Stage 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

# Metadata
LABEL maintainer="Platform God Contributors"
LABEL description="Platform God - Agent-driven repository governance system"
LABEL version="0.1.0"
LABEL org.opencontainers.image.title="Platform God"
LABEL org.opencontainers.image.description="Agent-driven repository governance and analysis framework"
LABEL org.opencontainers.image.version="0.1.0"

# Set runtime environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PGOD_VAR_DIR=/app/var \
    PGOD_LOG_LEVEL=INFO \
    PATH="/opt/venv/bin:$PATH"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Git is required for repository operations
    git \
    # ca-certificates for HTTPS connections
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Create non-root user for security
RUN groupadd -r pgod && \
    useradd -r -g pgod -s /bin/bash -d /app pgod

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create application directory structure
WORKDIR /app
RUN mkdir -p var/registry var/state var/audit var/cache var/artifacts prompts/agents && \
    chown -R pgod:pgod /app

# Copy application code
COPY --chown=pgod:pgod src/ ./src/
COPY --chown=pgod:pgod prompts/ ./prompts/
COPY --chown=pgod:pgod pyproject.toml ./

# Switch to non-root user
USER pgod

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ping').read()" || exit 1

# Default entrypoint supports both CLI and API modes
ENTRYPOINT ["python", "-m", "platform_god.cli"]

# Default command shows help (override with docker run / docker-compose)
CMD ["--help"]


# =============================================================================
# Usage Examples:
# =============================================================================
#
# CLI Mode - Run a command:
#   docker run --rm -v /path/to/repo:/repo platform-god inspect /repo
#   docker run --rm -v /path/to/repo:/repo platform-god agents list
#
# API Server Mode:
#   docker run -p 8000:8000 platform-god serve --port 8000
#
# With environment variables:
#   docker run -p 8000:8000 \
#     -e ANTHROPIC_API_KEY=your_key \
#     -e PGOD_LOG_LEVEL=DEBUG \
#     platform-god serve
#
# Volume mounts for persistent data:
#   docker run -p 8000:8000 \
#     -v pgod_var:/app/var \
#     -v /path/to/repo:/repo:ro \
#     platform-god serve
#
 =============================================================================
