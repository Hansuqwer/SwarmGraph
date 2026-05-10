# OrbStack Local Container Isolation

This guide shows how to run the SwarmGraph Gateway service shell in a local container using OrbStack (or any Docker-compatible runtime).

## Overview

OrbStack is a fast, lightweight Docker-compatible container runtime for macOS. SwarmGraph's `Dockerfile` uses standard Docker commands and works with OrbStack, Docker Desktop, or any Docker-compatible runtime—no OrbStack-specific dependencies or commands are required in the application code.

## Prerequisites

- OrbStack installed and running (or Docker Desktop)
- SwarmGraph repository cloned locally
- Optional service dependencies available via `[service]` extra

## Building the Image

From the repository root:

```bash
docker build -t swarmgraph-gateway:local .
```

The multi-stage build:
1. Installs `uv` and project dependencies with `[service]` extra
2. Creates a minimal runtime image with Python 3.12-slim
3. Runs as non-root user `swarmgraph` (UID 1000)
4. Exposes port 8000

## Running the Container

### Basic Run

```bash
docker run -p 8000:8000 swarmgraph-gateway:local
```

### With Environment Variables

Create an `.env.docker` file:

```bash
# Production profile (required for service shell)
AI_PROVIDER_GATEWAY_PROFILE=production

# Optional: strict readiness checks
AI_PROVIDER_GATEWAY_SERVICE_STRICT_READY=true

# Required when strict readiness is enabled
AI_PROVIDER_GATEWAY_TENANT=tenant-001
HIVE_SWARM_AUDIT_SECRET=replace-with-32-plus-random-bytes
HIVE_SWARM_AUDIT_SIGNING_ENABLED=true
HIVE_SWARM_AUDIT_FAIL_CLOSED=true
HIVE_SWARM_AUDIT_LOG_PATH=/data/audit/{tenant}/{swarm_id}.jsonl

# Optional: regulated/high-assurance audit durability
HIVE_SWARM_AUDIT_FSYNC_ENABLED=true

# Optional: gateway state paths for future mutation APIs
SWARMGRAPH_CACHE_SEMANTIC_DB_PATH=/data/cache/semantic.db
SWARMGRAPH_QUOTA_SQLITE_PATH=/data/quota/tracker.db
```

Run with environment file:

```bash
docker run -p 8000:8000 --env-file .env.docker swarmgraph-gateway:local
```

### With Persistent State Volume

For durable audit logs, cache, and quota state:

```bash
# Create a named volume
docker volume create swarmgraph-data

# Run with volume mounted
docker run -p 8000:8000 \
  --env-file .env.docker \
  -v swarmgraph-data:/data \
  swarmgraph-gateway:local
```

### Disposable Ephemeral Container

For testing without persistent state:

```bash
docker run --rm -p 8000:8000 \
  -e AI_PROVIDER_GATEWAY_PROFILE=production \
  swarmgraph-gateway:local
```

The `--rm` flag removes the container when it stops.

## Health Checks

The container includes a built-in health check that polls `/healthz` every 30 seconds.

Check container health:

```bash
docker ps
```

Look for `healthy` status in the `STATUS` column.

### Manual Health Checks

```bash
# Health endpoint (always returns ok)
curl http://localhost:8000/healthz

# Readiness endpoint (checks production profile)
curl http://localhost:8000/readyz

# Metrics endpoint (if prometheus-client installed)
curl http://localhost:8000/metrics
```

Expected responses:

```json
// /healthz
{"ok": true}

// /readyz (strict readiness disabled)
{"ok": true, "strict": false}

// /readyz (strict readiness enabled and production profile valid)
{"ok": true, "strict": true}
```

## OrbStack-Specific Features

OrbStack provides additional conveniences (all optional):

### Fast Builds

OrbStack's build cache is typically faster than Docker Desktop:

```bash
# Rebuild after code changes
docker build -t swarmgraph-gateway:local .
```

### Network Access

OrbStack containers can access `host.docker.internal` to reach services on the host:

```bash
# Example: connect to host PostgreSQL
docker run -p 8000:8000 \
  -e SWARMGRAPH_QUOTA_BACKEND=postgres \
  -e SWARMGRAPH_QUOTA_POSTGRES_URL=postgresql://user:pass@host.docker.internal:5432/swarmgraph \
  swarmgraph-gateway:local
```

### Volume Performance

OrbStack volumes use native filesystem performance (no virtualization overhead).

## Multi-Tenant Isolation

Run multiple isolated instances with different tenant IDs:

```bash
# Tenant A
docker run -d --name gateway-tenant-a -p 8001:8000 \
  -e AI_PROVIDER_GATEWAY_TENANT=tenant-a \
  -e HIVE_SWARM_AUDIT_SECRET=replace-with-32-plus-random-bytes \
  -e HIVE_SWARM_AUDIT_SIGNING_ENABLED=true \
  -e HIVE_SWARM_AUDIT_FAIL_CLOSED=true \
  -e HIVE_SWARM_AUDIT_LOG_PATH=/data/audit/{tenant}/{swarm_id}.jsonl \
  -v swarmgraph-data-a:/data \
  swarmgraph-gateway:local

# Tenant B
docker run -d --name gateway-tenant-b -p 8002:8000 \
  -e AI_PROVIDER_GATEWAY_TENANT=tenant-b \
  -e HIVE_SWARM_AUDIT_SECRET=replace-with-32-plus-random-bytes \
  -e HIVE_SWARM_AUDIT_SIGNING_ENABLED=true \
  -e HIVE_SWARM_AUDIT_FAIL_CLOSED=true \
  -e HIVE_SWARM_AUDIT_LOG_PATH=/data/audit/{tenant}/{swarm_id}.jsonl \
  -v swarmgraph-data-b:/data \
  swarmgraph-gateway:local
```

Each instance has isolated:
- Audit logs (scoped by tenant in JSONL/S3 backends)
- Semantic cache (tenant column in SQLite)
- Quota tracking (separate SQLite databases)

## Stopping and Cleanup

```bash
# Stop a running container
docker stop <container-id>

# Remove a stopped container
docker rm <container-id>

# Remove the image
docker rmi swarmgraph-gateway:local

# Remove a volume (WARNING: deletes all data)
docker volume rm swarmgraph-data
```

## Limitations

The current service shell is **read-only** and exposes only:
- `/healthz` - health check
- `/readyz` - readiness check with production profile validation
- `/metrics` - Prometheus metrics (if enabled)

No mutation APIs (routing, swarm execution) are exposed yet. This is intentional for the initial hosted deployment profile.

## Next Steps

For production hosted deployments:
- Add authentication boundary (API keys, JWT, mTLS)
- Bind tenant identity per request
- Add routing/swarm mutation APIs with tenant isolation
- Use shared backends (Redis quota, Postgres cache, S3 audit)
- Deploy to Kubernetes or cloud container service
- Configure ingress, TLS, and observability

See `docs/operations/production-profile.md` for production configuration details.
