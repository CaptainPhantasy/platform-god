# Platform God - Backup and Disaster Recovery Procedures

## Version
Document Version: 1.0
Last Updated: 2025-01-20
System: Platform God v0.1.0

---

## 1. Data Storage Locations

### 1.1 Persistent Data Directories

| Directory | Purpose | Backup Frequency | Retention |
|-----------|---------|------------------|-----------|
| `var/registry/` | Agent definitions and registry state | Daily | 90 days |
| `var/state/` | Execution history and run results | Daily | 30 days |
| `var/artifacts/` | Generated reports and artifacts | Daily | 90 days |
| `var/audit/` | Audit logs | Real-time | 365 days |
| `var/cache/` | LLM response cache | Weekly | 7 days |

### 1.2 Configuration Files

| File | Purpose | Backup Frequency |
|------|---------|------------------|
| `.env` | Environment configuration | On change |
| `pyproject.toml` | Dependencies and project config | On change |
| `chains.yaml` | Chain definitions | On change |

---

## 2. Backup Procedures

### 2.1 Automated Backup Script

```bash
#!/bin/bash
# backup_platform_god.sh
# Run: ./backup_platform_god.sh /path/to/backup/destination

BACKUP_DIR="${1:-/backups/platform_god}"
DATE=$(date +%Y%m%d_%H%M%S)
SOURCE_DIR="/path/to/PLATFORM GOD"

echo "Starting backup at $(date)"

# Create backup directory
mkdir -p "$BACKUP_DIR/$DATE"

# Backup critical data directories
tar -czf "$BACKUP_DIR/$DATE/registry.tar.gz" -C "$SOURCE_DIR" var/registry/
tar -czf "$BACKUP_DIR/$DATE/state.tar.gz" -C "$SOURCE_DIR" var/state/
tar -czf "$BACKUP_DIR/$DATE/artifacts.tar.gz" -C "$SOURCE_DIR" var/artifacts/
tar -czf "$BACKUP_DIR/$DATE/audit.tar.gz" -C "$SOURCE_DIR" var/audit/

# Backup configuration
tar -czf "$BACKUP_DIR/$DATE/config.tar.gz" -C "$SOURCE_DIR" .env chains.yaml

# Generate backup manifest
cat > "$BACKUP_DIR/$DATE/manifest.txt" << MANIFEST
Backup Date: $(date)
Platform God Version: $(pgod version)
Files Included:
  - registry.tar.gz (Agent definitions)
  - state.tar.gz (Execution history)
  - artifacts.tar.gz (Generated reports)
  - audit.tar.gz (Audit logs)
  - config.tar.gz (Configuration)
MANIFEST

echo "Backup completed: $BACKUP_DIR/$DATE"
```

### 2.2 Backup Schedule (Cron)

```cron
# Daily backup at 2 AM
0 2 * * * /path/to/backup_platform_god.sh /backups/platform_god

# Weekly full backup on Sunday at 3 AM
0 3 * * 0 /path/to/backup_platform_god.sh /backups/platform_god/weekly

# Cleanup old backups (keep daily for 7 days, weekly for 4 weeks)
0 4 * * * find /backups/platform_god -name "*.tar.gz" -mtime +7 -delete
```

---

## 3. Restoration Procedures

### 3.1 Full System Restoration

```bash
#!/bin/bash
# restore_platform_god.sh
# Run: ./restore_platform_god.sh /path/to/backup/20250120_020000

BACKUP_SOURCE="$1"
TARGET_DIR="/path/to/PLATFORM GOD"

echo "Restoring from backup: $BACKUP_SOURCE"

# Verify backup integrity
if [ ! -f "$BACKUP_SOURCE/manifest.txt" ]; then
    echo "Error: Invalid backup directory (missing manifest)"
    exit 1
fi

# Stop running services
pgod api stop 2>/dev/null || true
pkill -f "uvicorn.*platform_god" 2>/dev/null || true

# Restore data directories
tar -xzf "$BACKUP_SOURCE/registry.tar.gz" -C "$TARGET_DIR"
tar -xzf "$BACKUP_SOURCE/state.tar.gz" -C "$TARGET_DIR"
tar -xzf "$BACKUP_SOURCE/artifacts.tar.gz" -C "$TARGET_DIR"
tar -xzf "$BACKUP_SOURCE/audit.tar.gz" -C "$TARGET_DIR"

# Restore configuration (with confirmation)
read -p "Restore configuration? This will overwrite .env (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    tar -xzf "$BACKUP_SOURCE/config.tar.gz" -C "$TARGET_DIR"
fi

echo "Restoration complete"
echo "Please restart services: pgod api start"
```

### 3.2 Selective Restoration

**Restore Only Registry:**
```bash
tar -xzf /backups/platform_god/TIMESTAMP/registry.tar.gz -C /path/to/PLATFORM GOD
```

**Restore Only Audit Logs:**
```bash
tar -xzf /backs/platform_god/TIMESTAMP/audit.tar.gz -C /path/to/PLATFORM GOD
```

---

## 4. Disaster Recovery Scenarios

### 4.1 Scenario: Complete Server Loss

**Recovery Time Objective (RTO):** 4 hours
**Recovery Point Objective (RPO):** 24 hours

**Steps:**
1. Provision new server
2. Install Python 3.11+ and dependencies
3. Clone Platform God repository
4. Restore latest backup using `restore_platform_god.sh`
5. Update DNS/load balancer to point to new server
6. Verify health endpoints: `curl https://api.example.com/health/status`

### 4.2 Scenario: Registry Corruption

**Detection:** Agent listing fails with parsing errors

**Recovery Steps:**
1. Stop API server
2. Backup corrupted registry: `mv var/registry var/registry.corrupted.$(date +%s)`
3. Restore from backup: `tar -xzf /backups/latest/registry.tar.gz`
4. Restart API server
5. Verify: `pgod agents`

### 4.3 Scenario: Audit Log Loss

**Impact:** Loss of compliance/audit trail

**Prevention:**
- Stream audit logs to external log aggregation (e.g., Elasticsearch, CloudWatch)
- Enable audit log forwarding via notification channels

**Recovery Steps:**
1. Restore from backup (if available)
2. Check external log aggregation for missing entries
3. Document gap in audit trail

---

## 5. High Availability Setup

### 5.1 Multi-Instance Deployment

```yaml
# docker-compose-ha.yml
version: '3.8'
services:
  platform-god-1:
    image: platform-god:latest
    environment:
      - PG_STATE_PATH=/data/state
      - PG_REGISTRY_PATH=/data/registry
    volumes:
      - nfs-share:/data
    deploy:
      replicas: 1
      
  platform-god-2:
    image: platform-god:latest
    environment:
      - PG_STATE_PATH=/data/state
      - PG_REGISTRY_PATH=/data/registry
    volumes:
      - nfs-share:/data
    deploy:
      replicas: 1
      
  load-balancer:
    image: nginx:alpine
    ports:
      - "80:80"
    configs:
      - nginx.conf
```

### 5.2 Database Backend (Future Enhancement)

For production deployments requiring higher availability:
- Migrate from file-based storage to PostgreSQL
- Use streaming replication for HA
- Configure automated backups via `pg_dump`

---

## 6. Monitoring and Alerts

### 6.1 Health Check Monitoring

```bash
# Add to monitoring system (e.g., Prometheus, Nagios)
# Check every 30 seconds

#!/bin/bash
HEALTH_URL="http://localhost:8000/health/status"
RESPONSE=$(curl -s "$HEALTH_URL")

if echo "$RESPONSE" | grep -q '"status": "ok"'; then
    echo "OK: Platform God health check passed"
    exit 0
else
    echo "CRITICAL: Platform God health check failed"
    exit 2
fi
```

### 6.2 Backup Verification

```bash
# Weekly backup verification
#!/bin/bash
LATEST_BACKUP=$(ls -t /backups/platform_god | head -1)
tar -tzf "/backups/platform_god/$LATEST_BACKUP/registry.tar.gz" > /dev/null
if [ $? -eq 0 ]; then
    echo "Backup integrity verified: $LATEST_BACKUP"
else
    echo "ERROR: Backup corrupted: $LATEST_BACKUP"
fi
```

---

## 7. Contact and Escalation

| Issue Type | Contact | Escalation Path |
|------------|---------|-----------------|
| System outage | DevOps team | → CTO |
| Backup failure | Storage admin | → DevOps lead |
| Security incident | Security team | → CEO |
| Data corruption | DBA team | → CTO |

---

## Appendix A: File Integrity Checksums

Generate checksums for critical files:

```bash
# Generate
sha256sum var/registry/*.yaml > checksums.txt

# Verify
sha256sum -c checksums.txt
```

---

## Appendix B: LLM Cache Recovery

The LLM response cache (`var/cache/`) is non-critical and can be regenerated by re-running agents. No special recovery procedures needed.
