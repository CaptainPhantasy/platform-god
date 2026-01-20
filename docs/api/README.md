# API Documentation

Platform God provides a comprehensive REST API for all governance operations.

## Quick Reference

The API is implemented using FastAPI in `src/platform_god/api/`.

### Base URL

- Default: `http://localhost:8000`
- Health: `/health`
- API v1: `/api/v1/`
- OpenAPI docs: `/docs`

### Endpoints (37 total)

| Module | Endpoints | Description |
|--------|-----------|-------------|
| `/api/v1/agents` | 5 | List, get, execute agents, list classes/permissions |
| `/api/v1/chains` | 3 | List, execute, cancel chains |
| `/api/v1/runs` | 6 | List, get recent, get details, repository runs, latest by chain, delete |
| `/api/v1/registry` | 7 | List, types, index, CRUD entities, verify |
| `/health` | 5 | Health, ping, detailed, ready, live |
| `/metrics` | 6 | JSON, Prometheus, agent/chain/system metrics, reset, save |

## Starting the API

```bash
# Start API server using uvicorn directly
uvicorn platform_god.api.app:app --host 0.0.0.0 --port 8000

# Or with custom port
uvicorn platform_god.api.app:app --port 8080

# Run in background
nohup uvicorn platform_god.api.app:app --host 0.0.0.0 --port 8000 > /tmp/pgod_api.log 2>&1 &
```

**Note:** The CLI does not have a `serve` command. Use uvicorn directly to start the API server.

## Authentication

Authentication is enabled by default. Include the `X-User-ID` header in your requests:

```bash
curl -H "X-User-ID: test-user" http://localhost:8000/api/v1/chains
```

## Quick Examples

### List Available Chains

```bash
curl -H "X-User-ID: test-user" http://localhost:8000/api/v1/chains
```

### Execute a Chain

```bash
curl -X POST http://localhost:8000/api/v1/chains/discovery_analysis/execute \
  -H "X-User-ID: test-user" \
  -H "Content-Type: application/json" \
  -d '{
    "repository_path": "/path/to/repo",
    "mode": "dry_run"
  }'
```

### Check System Health

```bash
curl http://localhost:8000/health
```

### Get Metrics

```bash
curl -H "X-User-ID: test-user" http://localhost:8000/api/v1/metrics
```

## OpenAPI Documentation

Once the server is running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

These provide interactive API documentation with request/response examples.

## See Also

- `src/platform_god/api/app.py` - Main application
- `src/platform_god/api/routes/` - Route implementations
- [Getting Started Guide](../GETTING_STARTED.md) - Complete setup instructions
