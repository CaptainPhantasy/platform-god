# Security Policy

## Supported Versions

| Version | Supported Until |
|---------|-----------------|
| 0.1.x   | Current         |

## Reporting a Vulnerability

**DO NOT** open a public issue for security vulnerabilities.

### How to Report

Send an email to security@example.com with the following details:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if known)

We will respond within 48 hours with:
- Confirmation of receipt
- Severity assessment
- Estimated timeline for fix
- Planned disclosure date

### Disclosure Policy

- We follow responsible disclosure (90-day window)
- Security fixes will be released as soon as possible
- Public disclosure coordinated after fix is available

## Current Security Status

### Known Issues (as of 2026-01-16)

| Severity | Issue | Status | Location |
|----------|-------|--------|----------|
| **MEDIUM** | No rate limiting on API | Open | N/A |
| **LOW** | Try-except-pass patterns | Open | `notifications/dispatcher.py` |

### Remediation Plan

1. **MEDIUM Priority** (Q1 2026)
   - [ ] Add API key authentication documentation
   - [ ] Add rate limiting using slowapi or similar

2. **MEDIUM Priority** (Q1 2026)
   - [ ] Add input validation for all API endpoints
   - [ ] Implement request size limits

3. **LOW Priority** (Q2 2026)
   - [ ] Remove try-except-pass patterns
   - [ ] Add proper exception handling

### Recently Resolved (2026-01-16)

- **RESOLVED**: MD5 replaced with SHA256 for all fingerprinting operations (`state/manager.py`)
- **RESOLVED**: Authentication now enabled by default (`api/app.py`). Auth is enforced on all endpoints except public paths (`/health`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`). Configure via `PG_REQUIRE_AUTH` environment variable.

## Security Best Practices

### For Users

1. **API Keys**
   - Never commit API keys to version control
   - Use environment variables or secret managers
   - Rotate keys regularly

2. **Authentication**
   - Authentication is **enabled by default** via `PG_REQUIRE_AUTH=true`
   - Provide `X-User-ID` header for authenticated requests
   - Use `X-API-Key` header as an alternative authentication method
   - To disable auth (not recommended for production), set `PG_REQUIRE_AUTH=false`
   - Consider OAuth2/JWT integration for production deployments

3. **Network Security**
   - Run behind a reverse proxy (nginx, traefik)
   - Enable HTTPS/TLS in production
   - Use firewall rules to restrict access

### For Developers

1. **Before Committing**
   ```bash
   # Run security linter
   bandit -r src/

   # Check for secrets
   git-secrets --scan

   # Run all tests
   pytest
   ```

2. **Dependencies**
   - Review dependency updates
   - Run `safety check` regularly
   - Keep dependencies updated

3. **Code Review**
   - All code changes require review
   - Security-sensitive changes require 2 reviewers
   - Use branch protection rules

## Security Features

### Implemented

| Feature | Status | Notes |
|---------|--------|-------|
| Audit logging | Implemented | `var/audit/registry_log.jsonl` |
| Entity integrity | Implemented | SHA256 checksums |
| Atomic writes | Implemented | Write-replace pattern |
| Authentication enforcement | Implemented | Enabled by default (configurable via `PG_REQUIRE_AUTH`) |
| CORS middleware | Implemented | Configurable origins |
| Health endpoints | Implemented | State, registry, disk checks |
| Metrics endpoint | Implemented | JSON/Prometheus formats |

### Not Yet Implemented

| Feature | Priority | Status |
|---------|----------|--------|
| Rate limiting | HIGH | Not implemented |
| Input validation | MEDIUM | Partial |
| Secret scanning | MEDIUM | Agent prompt only |
| SQL injection protection | LOW | N/A (JSON storage) |

## Dependency Security

### Scanning

We use [Safety](https://pyup.io/safety/) for dependency vulnerability scanning:

```bash
safety check
```

### Current Status

As of 2026-01-16: **0 known vulnerabilities** in dependencies.

### Vulnerability Response

When a vulnerability is found in a dependency:
1. Assess severity and impact
2. Update to patched version within SLA:
   - Critical: 48 hours
   - High: 7 days
   - Medium: 30 days
   - Low: Next release

## Security Audits

| Date | Auditor | Scope | Report |
|------|---------|-------|--------|
| Pending | - | - | - |

## License

This project is licensed under the MIT License.

## Contact

- Security email: security@example.com
- GitHub Security: [Security Advisories](https://github.com/platform-god-project/platform-god/security/advisories)

---

## Recently Resolved (2026-01-16 Swarm Fix Deployment)

### Critical Security Fixes

| Issue | Severity | Fix Description |
|-------|----------|-----------------|
| **Auth not enforced by default** | HIGH | `AuthMiddleware` now enabled by default via `PG_REQUIRE_AUTH=true` |
| **No rate limiting** | HIGH | Implemented rate limiting (10 req/sec default) via `RateLimitMiddleware` |
| **No request size limits** | HIGH | Implemented `SizeLimitMiddleware` (10 MB default) |
| **Subprocess without shell=False** | MEDIUM | Added explicit `shell=False` to all `subprocess.run()` calls |
| **MD5 used for fingerprints** | MEDIUM | Verified SHA256 migration complete, updated documentation |
| **Documentation placeholders** | LOW | Replaced all `[INSERT ...]` placeholders with actual values |

### New Security Features Implemented

| Feature | Description |
|---------|-------------|
| **JWT Authentication** | Full JWT implementation with token generation, validation, expiration |
| **API Key Authentication** | SHA-256 hashed API key validation via `x-api-key` header |
| **Input Validation Middleware** | Content-Type whitelist, query sanitization, JSON parsing |
| **Rate Limiting** | Per-IP rate limiting with configurable windows, headers, and exempt paths |
| **Request Size Limits** | Configurable max request/response sizes with 413 responses |

### New Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_REQUIRE_AUTH` | `true` | Enable authentication enforcement |
| `PG_RATE_LIMIT` | `10/second` | Rate limit per IP address |
| `PG_MAX_REQUEST_SIZE` | `10M` | Maximum request body size |
| `PG_MAX_RESPONSE_SIZE` | `50M` | Response size warning threshold |
| `PG_JWT_SECRET` | *(warning if unset)* | JWT signing secret |
| `PG_API_KEYS` | *(empty)* | Comma-separated SHA-256 API key hashes |
| `PG_VALIDATION_STRICT` | `true` | Enable strict input validation |

### New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/token` | POST | Generate JWT access token |
| `/api/v1/auth/token/validate` | POST | Validate a JWT token |
| `/api/v1/auth/me` | GET | Get current authenticated user info |
| `/api/v1/auth/config` | GET | Get auth configuration |

### Test Coverage Added

- 235+ new tests covering:
  - Rate limiting middleware
  - Size limit middleware
  - Input validation middleware
  - JWT authentication
  - Automations module
  - Notifications module

---

**Last Updated:** 2026-01-16
