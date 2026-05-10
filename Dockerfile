# syntax=docker/dockerfile:1

# Multi-stage build for SwarmGraph Gateway service shell
# Builds a minimal production image with optional [service] dependencies

# Stage 1: Builder - install uv and dependencies
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy all source code (needed for editable installs)
COPY pyproject.toml uv.lock ./
COPY packages/ packages/

# Install dependencies into a virtual environment
# Use --no-dev to exclude dev dependencies
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache -e "./packages/swarm-shared" && \
    uv pip install --no-cache -e "./packages/hive-swarm" && \
    uv pip install --no-cache -e "./packages/ai-provider-swarm-gateway[service]"

# Stage 2: Runtime - minimal production image
FROM python:3.12-slim

# Create non-root user
RUN groupadd -r swarmgraph && \
    useradd -r -g swarmgraph -u 1000 swarmgraph && \
    mkdir -p /app /data && \
    chown -R swarmgraph:swarmgraph /app /data

# Copy virtual environment from builder
COPY --from=builder --chown=swarmgraph:swarmgraph /opt/venv /opt/venv

# Copy application code
COPY --from=builder --chown=swarmgraph:swarmgraph /app/packages /app/packages

# Set working directory and user
WORKDIR /app
USER swarmgraph

# Add venv to PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose service port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz').read()"

# Run the service
# Use exec form to ensure proper signal handling
CMD ["uvicorn", "ai_provider_swarm_gateway.service:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
