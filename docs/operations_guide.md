# Operations Guide

**Date:** 2026-06-18
**Purpose:** Guide for operating the Odoo Dashboard sync platform in production

---

## Table of Contents

1. [Production Deployment](#production-deployment)
2. [Daily Operations](#daily-operations)
3. [Monitoring](#monitoring)
4. [Recovery Procedures](#recovery-procedures)
5. [Backup Strategy](#backup-strategy)

---

## Production Deployment

### Environment Setup

#### 1. Server Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| Memory | 4 GB | 8+ GB |
| Disk | 50 GB | 100+ GB |
| Python | 3.10 | 3.11+ |
| PostgreSQL | 12 | 14+ |

#### 2. Environment Variables

Create `/opt/odoo-sync/.env`:

```bash
# Odoo Configuration
ODOO_URL=https://odoo.example.com
ODOO_API_KEY=<your-api-key>
ODOO_DB=<database-name>

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sync_dashboard
POSTGRES_USER=sync_user
POSTGRES_PASSWORD=<strong-password>

# Logging
LOG_LEVEL=INFO
LOG_DIR=/var/log/odoo-sync

# Sync Settings
SYNC_BATCH_SIZE=1000
```

#### 3. Database Setup

```bash
# Create database
sudo -u postgres psql -c "CREATE DATABASE sync_dashboard;"

# Create user
sudo -u postgres psql -c "CREATE USER sync_user WITH PASSWORD '<password>';"

# Grant permissions
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE sync_dashboard TO sync_user;"
sudo -u postgres psql -c "ALTER USER sync_user CREATEDB;"
```

#### 4. Installation

```bash
# Clone repository
git clone <repo-url> /opt/odoo-sync
cd /opt/odoo-sync

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set permissions
chown -R sync_user:sync_user /opt/odoo-sync
chmod 600 /opt/odoo-sync/.env
```

#### 5. Service Setup (systemd)

Create `/etc/systemd/system/odoo-sync.service`:

```ini
[Unit]
Description=Odoo PostgreSQL Sync Service
After=postgresql.service

[Service]
Type=simple
User=sync_user
WorkingDirectory=/opt/odoo-sync
Environment=PATH=/opt/odoo-sync/venv/bin
ExecStart=/opt/odoo-sync/venv/bin/python -m src.main --mode incremental
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable odoo-sync
sudo systemctl start odoo-sync
```

---

## Daily Operations

### Running Full Sync

Run full sync for initial setup or recovery:

```bash
cd /opt/odoo-sync
source venv/bin/activate
python -m src.main --mode full
```

### Running Incremental Sync

Regular scheduled sync:

```bash
python -m src.main --mode incremental
```

### Running for Specific Model

```bash
# Full sync single model
python -m src.main --mode full --models sale.order

# Incremental sync single model
python -m src.main --mode incremental --models stock.quant
```

### Using Cron for Scheduled Syncs

Add to crontab (`crontab -e`):

```bash
# Every hour
0 * * * * cd /opt/odoo-sync && /opt/odoo-sync/venv/bin/python -m src.main --mode incremental >> /var/log/odoo-sync/cron.log 2>&1

# Every day at midnight
0 0 * * * cd /opt/odoo-sync && /opt/odoo-sync/venv/bin/python -m src.main --mode full >> /var/log/odoo-sync/full-cron.log 2>&1
```

---

## Monitoring

### Check Sync Status

```bash
# Check if sync is running
ps aux | grep "src.main"

# View recent logs
tail -100 /var/log/odoo-sync/sync.log

# Check sync state in database
psql -U sync_user -d sync_dashboard -c "SELECT model_name, status, last_sync_date, records_synced FROM sync_state ORDER BY model_name;"
```

### Key Metrics to Monitor

| Metric | Normal Range | Alert Threshold |
|--------|--------------|----------------|
| Sync duration | < 30 min | > 2 hours |
| Records synced | Varies by model | 0 (stale) |
| Error rate | < 1% | > 5% |
| sync_state status | COMPLETED | FAILED |

### Check for Stale Syncs

```sql
-- Find models not synced in 24 hours
SELECT model_name, status, last_sync_date, NOW() - last_sync_date as stale_duration
FROM sync_state
WHERE status != 'COMPLETED' 
   OR last_sync_date < NOW() - INTERVAL '24 hours'
ORDER BY last_sync_date;
```

### View Error Reports

```bash
# List recent error reports
ls -la reports/errors/

# View summary
cat reports/errors/summary_latest.json | jq .
```

---

## Recovery Procedures

### Failed Sync Recovery

#### Step 1: Diagnose the Failure

```bash
# Check sync state
python scripts/diagnose_sync_state.py

# Check logs for errors
grep -i error /var/log/odoo-sync/sync.log | tail -50
```

#### Step 2: Fix the Issue

Common issues and fixes:

**Schema Error:**
```bash
# Apply schema fixes
python scripts/repair_schema.py
```

**Checkpoint Corruption:**
```sql
-- Reset checkpoint for specific model
UPDATE sync_state 
SET status = 'PENDING', 
    last_sync_date = NULL, 
    last_sync_id = NULL 
WHERE model_name = 'problematic.model';
```

**Authentication Failure:**
```bash
# Verify credentials
grep ODOO_API_KEY /opt/odoo-sync/.env
# Regenerate key if needed in Odoo settings
```

#### Step 3: Re-run Sync

```bash
# Full sync for failed model
python -m src.main --mode full --models problematic.model
```

### Corrupted Checkpoint Recovery

#### Option 1: Full Resync

```sql
-- Reset ALL checkpoints
UPDATE sync_state SET status = 'PENDING', last_sync_date = NULL, last_sync_id = NULL;

-- Run full sync
python -m src.main --mode full
```

#### Option 2: Selective Reset

```sql
-- Reset specific model
UPDATE sync_state 
SET status = 'PENDING',
    last_sync_date = NULL,
    last_sync_id = NULL 
WHERE model_name = 'sale.order';

-- Run full sync for that model
python -m src.main --mode full --models sale.order
```

### Database Restore Recovery

#### Step 1: Restore PostgreSQL Backup

```bash
# Stop sync service
sudo systemctl stop odoo-sync

# Restore database
pg_restore -U postgres -d sync_dashboard /path/to/backup.dump

# Restart sync service
sudo systemctl start odoo-sync
```

#### Step 2: Verify Data

```sql
-- Check record counts
SELECT model_name, COUNT(*) FROM sale_order GROUP BY model_name;

-- Compare with Odoo (via Odoo interface)
```

### Schema Mismatch Recovery

If Odoo schema drifted from PostgreSQL:

```bash
# Force schema refresh
python -m src.main --mode full --force-schema
```

Or manually apply migrations:

```bash
# View recommendations
cat reports/schema_recommendations/migration_suggestions.sql

# Apply manually (review first!)
psql -U sync_user -d sync_dashboard -f reports/schema_recommendations/migration_suggestions.sql
```

---

## Backup Strategy

### PostgreSQL Backup

#### Full Database Backup

```bash
# Daily backup (via cron)
pg_dump -U sync_user -d sync_dashboard -F c -f /backups/sync_dashboard_$(date +%Y%m%d).dump
```

#### Continuous Archiving (Point-in-Time Recovery)

Add to `postgresql.conf`:

```bash
wal_level = replica
max_wal_senders = 3
wal_keep_size = 1GB
archive_mode = on
archive_command = 'cp %p /archive/wal/%f'
```

### Sync State Backup

```sql
-- Export sync state
COPY (SELECT * FROM sync_state ORDER BY model_name) 
TO '/backups/sync_state.csv' 
WITH (FORMAT csv, HEADER);
```

### Backup Verification

```bash
# Test restore
pg_restore -U postgres -d sync_dashboard_test /backups/sync_dashboard_latest.dump

# Verify data
psql -U sync_user -d sync_dashboard_test -c "SELECT COUNT(*) FROM sale_order;"
```

### Retention Policy

| Backup Type | Retention | Location |
|-------------|-----------|----------|
| Daily dumps | 7 days | /backups/daily/ |
| Weekly dumps | 4 weeks | /backups/weekly/ |
| Monthly dumps | 12 months | /backups/monthly/ |
| WAL archives | 7 days | /archive/wal/ |

### Backup Script Example

Create `/opt/odoo-sync/scripts/backup.sh`:

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/backups
RETENTION_DAYS=7

# Create backup directory
mkdir -p $BACKUP_DIR/daily

# Backup database
pg_dump -U sync_user -d sync_dashboard -F c -f $BACKUP_DIR/daily/sync_$DATE.dump

# Backup sync state
psql -U sync_user -d sync_dashboard -c "COPY sync_state TO '$BACKUP_DIR/daily/sync_state_$DATE.csv' WITH (FORMAT csv, HEADER);"

# Cleanup old backups
find $BACKUP_DIR/daily -name "sync_*" -mtime +$RETENTION_DAYS -delete

# Log
echo "$(date): Backup completed: $BACKUP_DIR/daily/sync_$DATE.dump" >> /var/log/odoo-sync/backup.log
```

Make executable and schedule:

```bash
chmod +x /opt/odoo-sync/scripts/backup.sh
# Add to crontab:
0 2 * * * /opt/odoo-sync/scripts/backup.sh
```

---

## Security Best Practices

### Secrets Management

1. **Never commit secrets to git**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Use environment-specific .env files**
   - `.env.production`
   - `.env.staging`

3. **Rotate API keys regularly**

### Database Permissions

```sql
-- Create dedicated sync user with minimal permissions
CREATE USER sync_readonly WITH PASSWORD '...';
GRANT CONNECT ON DATABASE sync_dashboard TO sync_readonly;
GRANT USAGE ON SCHEMA public TO sync_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sync_readonly;

-- For sync operations (needs write)
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sync_user;
```

### Network Security

- Restrict Odoo access to sync server IP
- Use SSL/TLS for all connections
- Firewall Odoo instance to only allow sync server

---

## Troubleshooting Quick Reference

| Problem | Quick Fix |
|---------|-----------|
| Incremental sync re-fetches records | Check `sync_state` for NULL/FAILED status |
| Full sync every time | `UPDATE sync_state SET status='PENDING'` |
| Schema errors | Run `python scripts/repair_schema.py` |
| Authentication failure | Verify API key in `.env` |
| Database connection timeout | Check PostgreSQL is running |
| Out of disk space | Clean old backups, `VACUUM` database |
