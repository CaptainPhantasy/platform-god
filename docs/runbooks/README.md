# Runbooks

Operational procedures for common Platform God tasks.

## Quick Troubleshooting

### Agent Fails to Load
- Verify agent prompt file exists in `prompts/agents/`
- Check prompt format matches contract specification
- Run `pgod agents` to verify agent registration

### Chain Execution Stops
- Check audit logs in `var/audit/execution_*.jsonl`
- Verify repository root is accessible
- Ensure required inputs are provided
- Try `--mode dry_run` to validate prechecks

### LLM API Errors
- Verify `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set
- Check network connectivity to API endpoint
- Verify API quota is not exceeded
- Test with `--mode simulated` to bypass API

### History Command Shows No Runs
- Ensure you're using the correct repository path
- Check that runs were executed with `--record` flag
- Verify `var/state/` directory exists and is readable
- Try absolute path instead of relative path

### API Server Won't Start
- Verify port is not already in use: `lsof -i :8000`
- Check Python dependencies: `pip install -e .`
- Ensure virtual environment is activated
- Try alternative port: `uvicorn platform_god.api.app:app --port 8080`

### Permission Errors on `var/`
- Fix permissions: `chmod -R 755 var/`
- Ensure directory ownership is correct
- Check disk space: `df -h`

## Common Operations

### Starting the API Server

```bash
# Development server with auto-reload
uvicorn platform_god.api.app:app --host 0.0.0.0 --port 8000 --reload

# Production server (background)
nohup uvicorn platform_god.api.app:app --host 0.0.0.0 --port 8000 > /tmp/pgod_api.log 2>&1 &

# Check server health
curl http://localhost:8000/health
```

### Running Analysis Chains

```bash
# Quick validation (no API key needed)
pgod run discovery /path/to/repo --mode dry_run

# Full analysis with LLM
pgod run full_analysis /path/to/repo --mode live --record

# Security scan
pgod run security /path/to/repo --mode live -o security_report.json
```

### Viewing Execution History

```bash
# List recent runs
pgod history /path/to/repo

# Show last 5 runs
pgod history /path/to/repo --limit 5

# Inspect specific run
pgod inspect run_20240115123456
```

### Checking System Status

```bash
# Health check
pgod monitor --health

# Show metrics
pgod monitor --metrics

# Recent runs with auto-refresh
pgod monitor --recent 20 --watch
```

## Performance Tuning

### Large Repository Performance

For repositories with 100K+ files:
- Use `--mode dry_run` first to validate
- Consider running specific chains instead of `full_analysis`
- Increase LLM timeout: `export PG_LLM_TIMEOUT=120`
- Monitor memory usage: `pgod monitor --metrics`

### API Rate Limiting

If hitting rate limits:
- Reduce concurrent requests
- Increase rate limit window in middleware config
- Use batch operations where available
- Cache results in `var/cache/`

## Recovery Procedures

### Corrupted State Files

```bash
# Backup existing state
cp -r var/state var/state.backup

# Reset state (WARNING: loses history)
rm var/state/index.json
rm var/state/runs/*.json

# Re-index from repository
pgod run discovery /path/to/repo --mode dry_run --record
```

### Registry Corruption

```bash
# Backup registry
cp -r var/registry var/registry.backup

# Verify registry integrity
python -c "from platform_god.registry.storage import RegistryStorage; s = RegistryStorage(); print(s.verify())"

# Rebuild from scratch if needed
rm var/registry/*.json
```

## Monitoring

### Log Locations

- API logs: `/tmp/pgod_api.log` (if using background mode)
- Audit trails: `var/audit/executions_YYYYMMDD.jsonl`
- Run records: `var/state/runs/run_*.json`
- Registry logs: `var/registry/registry_log.jsonl`

### Health Monitoring

```bash
# Continuous monitoring
watch -n 5 'curl -s http://localhost:8000/health | jq'

# Check disk space
df -h /path/to/platform-god/var/

# Monitor active runs
ls -ltr var/state/runs/ | tail -10
```
