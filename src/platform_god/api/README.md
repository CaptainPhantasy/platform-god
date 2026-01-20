# PLATFORM GOD - API Module

FastAPI REST API for Platform God.

## Quick Start

```bash
# Start the server
pgod serve

# Access documentation
open http://localhost:8000/docs
```

## Architecture

- `app.py` - FastAPI application factory
- `routes/` - API endpoint modules (agents, chains, health, metrics, registry, runs)
- `middleware/` - Auth, CORS, logging, rate limiting, size limit
- `schemas/` - Pydantic request/response models

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `PG_REQUIRE_AUTH` | `true` | Enable authentication |
| `PG_API_KEY` | - | API key for authentication |
| `PG_RATE_LIMIT` | `100` | Requests per minute |

## Endpoints

See `/docs` (OpenAPI/Swagger) when server is running for full API reference.
