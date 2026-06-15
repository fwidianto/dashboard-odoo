# Odoo to PostgreSQL Synchronization Platform

A production-ready, metadata-driven synchronization platform that bridges Odoo ERP with PostgreSQL databases. Built with Python 3.12, SQLAlchemy, and designed for extensibility.

## Features

- **Metadata-Driven Architecture**: Configure Odoo models and fields via YAML - no code changes needed
- **API Key Authentication**: Secure authentication using Odoo API keys (password auth deprecated)
- **Incremental Synchronization**: Uses `write_date` for efficient delta syncs
- **Automatic Schema Evolution**: Creates tables and adds columns automatically
- **UPSERT Operations**: Uses PostgreSQL `INSERT ON CONFLICT DO UPDATE`
- **Dual Sync Modes**: Full sync and incremental sync supported
- **Scheduled Execution**: APScheduler-based job scheduling
- **REST API Ready**: FastAPI integration for production deployment
- **Comprehensive Logging**: Structured logging with structlog
- **State Tracking**: Persistent sync state in `sync_state` table
- **Health Monitoring**: `/health`, `/sync-status`, `/sync-history` endpoints

## Project Structure

```
odoo_postgres_sync/
├── config/
│   └── models.yaml          # Model configuration (add/edit models here)
├── migrations/               # Alembic database migrations
│   ├── versions/            # Migration scripts
│   ├── env.py               # Migration environment
│   └── script.py.mako       # Migration template
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point
│   ├── api.py               # FastAPI REST API (future)
│   ├── clients/
│   │   ├── odoo_client.py   # Odoo XML-RPC client
│   │   └── postgres_client.py # PostgreSQL SQLAlchemy client
│   ├── engine/
│   │   ├── sync_engine.py   # Core synchronization logic
│   │   └── scheduler.py     # Job scheduling
│   ├── models/
│   │   ├── __init__.py
│   │   ├── config.py        # Pydantic config models
│   │   └── state.py         # Sync state models
│   ├── state/
│   │   └── state_manager.py # State persistence
│   └── utils/
│       ├── __init__.py
│       ├── config_loader.py # YAML config loading
│       ├── logging.py       # Logging setup
│       └── settings.py      # Environment settings
├── tests/                   # Unit tests
├── .env.example             # Environment template
├── requirements.txt         # Python dependencies
├── pytest.ini              # Test configuration
├── alembic.ini             # Alembic configuration
└── README.md
```

## Quick Start

### 1. Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env
```

Configure your Odoo and PostgreSQL connections in `.env`:

```env
ODOO_URL=http://your-odoo-server:8069
ODOO_DB=your_database
ODOO_USERNAME=your_username

# Authentication - API Key is recommended for security
ODOO_API_KEY=your_api_key_here
# ODOO_PASSWORD=your_password  # DEPRECATED - only use if API key not available

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sync_database
POSTGRES_USER=sync_user
POSTGRES_PASSWORD=secure_password
```

### 3. Configure Models

Edit `config/models.yaml` to define which Odoo models to synchronize:

```yaml
models:
  - odoo_model: res.partner
    postgres_table: res_partner
    description: "Synchronize Odoo contacts"
    fields:
      - odoo_field: id
        postgres_column: id
        postgres_type: INTEGER
        primary_key: true
        nullable: false
      - odoo_field: name
        postgres_column: name
        postgres_type: VARCHAR(255)
      - odoo_field: email
        postgres_column: email
        postgres_type: VARCHAR(255)
      - odoo_field: write_date
        postgres_column: write_date
        postgres_type: TIMESTAMP
        is_sync_date: true
```

### 4. Run Synchronization

```bash
# Full sync (all records)
python -m src.main --mode full

# Incremental sync (only changed records)
python -m src.main --mode incremental

# Sync specific models
python -m src.main --models res.partner product.product

# Validate configuration
python -m src.main --validate

# Check sync status
python -m src.main --status

# Reset sync state for a model
python -m src.main --reset --models res.partner
```

## Command Line Interface

### Main Sync Command

```bash
python -m src.main [OPTIONS]

Options:
  --mode {full,incremental}    Sync mode
  --models MODEL [MODEL ...]   Specific models to sync
  --config PATH               Path to models.yaml
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
  --log-file FILE             Log file path
  --validate                  Validate configuration only
  --status                    Show sync status
  --reset                     Reset sync state
```

### Scheduler Command

```bash
python -m src.engine.scheduler [OPTIONS]

Options:
  --interval MINUTES          Incremental sync interval (default: 15)
  --full-sync-hour HOUR       Hour for daily full sync (default: 2)
  --full-sync-minute MINUTE   Minute for full sync (default: 0)
  --run-immediately           Run sync before scheduling
  --log-level LEVEL           Logging level
```

## Scheduled Execution

### Using the Built-in Scheduler

```bash
# Run scheduler with 15-minute incremental syncs
python -m src.engine.scheduler --interval 15 --run-immediately

# Run with daily full sync at 3:00 AM
python -m src.engine.scheduler --interval 15 --full-sync-hour 3
```

### Cron Example

Add to crontab for external scheduling:

```bash
# Every 15 minutes - incremental sync
*/15 * * * * cd /path/to/odoo_postgres_sync && python -m src.main --mode incremental >> /var/log/sync.log 2>&1

# Daily at 2:00 AM - full sync
0 2 * * * cd /path/to/odoo_postgres_sync && python -m src.main --mode full >> /var/log/sync_full.log 2>&1
```

### Systemd Service (Linux)

Create `/etc/systemd/system/odoo-sync.service`:

```ini
[Unit]
Description=Odoo PostgreSQL Sync Service
After=postgresql.service network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/odoo_postgres_sync
Environment=PYTHONPATH=/path/to/odoo_postgres_sync
ExecStart=/path/to/venv/bin/python -m src.engine.scheduler --interval 15
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Adding New Models

To add a new Odoo model to synchronize:

1. **Edit `config/models.yaml`**:

```yaml
models:
  # ... existing models ...

  - odoo_model: stock.quant
    postgres_table: stock_quant
    description: "Synchronize stock quantities"
    fields:
      - odoo_field: id
        postgres_column: id
        postgres_type: INTEGER
        primary_key: true
        nullable: false
      - odoo_field: product_id
        postgres_column: product_id
        postgres_type: INTEGER
      - odoo_field: quantity
        postgres_column: quantity
        postgres_type: NUMERIC(12, 3)
      - odoo_field: location_id
        postgres_column: location_id
        postgres_type: INTEGER
      - odoo_field: write_date
        postgres_column: write_date
        postgres_type: TIMESTAMP
        is_sync_date: true
```

2. **Run sync** - the table and columns will be created automatically:

```bash
python -m src.main --mode full
```

## Supported PostgreSQL Types

| YAML Type | PostgreSQL Type |
|-----------|-----------------|
| `INTEGER` | INTEGER |
| `BIGINT` | BIGINT |
| `VARCHAR(n)` | VARCHAR(n) |
| `TEXT` | TEXT |
| `BOOLEAN` | BOOLEAN |
| `NUMERIC(p,s)` | NUMERIC(precision, scale) |
| `TIMESTAMP` | TIMESTAMP |
| `DATE` | DATE |
| `UUID` | UUID |
| `JSONB` | TEXT (stored as JSON) |

## API Reference (Future FastAPI Integration)

The API can be enabled for HTTP-based control:

```bash
# Install FastAPI dependencies
pip install fastapi uvicorn

# Run API server
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/status` | Sync status for all models |
| POST | `/sync` | Trigger sync operation |
| POST | `/sync/{model_name}` | Sync specific model |
| POST | `/reset` | Reset sync state |
| GET | `/models` | List configured models |
| POST | `/scheduler/start` | Start scheduler |
| POST | `/scheduler/stop` | Stop scheduler |
| GET | `/scheduler/status` | Scheduler status |
| GET | `/validate` | Validate configuration |

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Sync Engine                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Odoo Client │  │  PostgreSQL │  │   State Manager     │  │
│  │  (XML-RPC)  │  │  (SQLAlchemy)│  │ (sync_state table) │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │              │
│         └────────────────┼─────────────────────┘              │
│                          ▼                                    │
│              ┌───────────────────────┐                        │
│              │   Configuration       │                        │
│              │   (models.yaml)       │                        │
│              └───────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### Sync Flow

1. **Initialize**: Load config, test connections, ensure tables exist
2. **Query Odoo**: Use `search_read` with domain filters
3. **Transform**: Convert Odoo records to PostgreSQL format
4. **Upsert**: Insert/update records using `ON CONFLICT`
5. **Track State**: Update `sync_state` table with last sync info
6. **Report**: Return statistics and any errors

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_sync_engine.py -v
```

## Troubleshooting

### Common Issues

**Connection refused to Odoo**
- Verify Odoo server is running
- Check URL in `.env` file
- Ensure firewall allows connection

**Authentication Errors**
- **API Key authentication failed**: Verify the API key is valid and associated with the user
  - Generate an API key in Odoo: Settings → User → API Key
  - Ensure the key hasn't expired or been revoked
- **Password authentication deprecated**: Consider migrating to API key
  - Set `ODOO_API_KEY` instead of `ODOO_PASSWORD`
  - See: [Odoo API Key Documentation](https://www.odoo.com/documentation/17.0/developer/reference/external_api.html)
- **Both methods fail**: Check that the username matches an existing Odoo user
- **User lacks permissions**: Ensure the user has access to the models being synced

**Table not found**
- Run full sync to create tables
- Check table name in `models.yaml`

**Missing columns**
- Run full sync to add new columns
- Check field names match Odoo model

### Authentication Methods

The platform supports two authentication methods:

| Method | Environment Variable | Security | Recommendation |
|--------|-------------------|----------|----------------|
| API Key | `ODOO_API_KEY` | High | **Preferred** |
| Password | `ODOO_PASSWORD` | Low | Deprecated |

#### Generating an Odoo API Key

1. Log in to Odoo as the target user
2. Go to Settings → Users & Companies → Users
3. Open the user profile
4. Click "Preferences" or "Change API Key"
5. Generate a new API key (copy it immediately - it won't be shown again)

#### Security Best Practices

- **Use API keys**: They don't expose user passwords
- **Rotate keys periodically**: Regenerate keys every 90 days
- **Use least privilege**: Create dedicated API users with minimal permissions
- **Store securely**: Use environment variables or secret management, never in code

### Debug Mode

```bash
# Enable debug logging
python -m src.main --log-level DEBUG --log-file debug.log
```

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions welcome! Please read the contribution guidelines and submit pull requests.