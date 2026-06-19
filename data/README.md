# Data Directory

This directory contains data files used by the Tent of Trials platform.

## Data Generator

The `tools/data_generator.py` script generates realistic-looking market data for development and testing. It supports deterministic output via seed control.

### Usage

```bash
# Generate with a specific seed (deterministic)
python3 tools/data_generator.py --seed 42

# Generate with a random seed and print it for reproduction
python3 tools/data_generator.py --print-seed

# Generate with specific counts
python3 tools/data_generator.py --seed 42 --users 100 --orders 500 --trades 1000
```

### Deterministic Output

When the same seed and arguments are provided, the output is byte-for-byte identical. This is useful for:

- Test fixtures that need to be reproducible
- Benchmark datasets that must be consistent
- Debugging specific data patterns

Example:
```bash
# These two commands produce identical output
python3 tools/data_generator.py --seed 42 --output-dir ./run1
python3 tools/data_generator.py --seed 42 --output-dir ./run2
```

### Seed Metadata

Generated data includes a `metadata.json` file with the seed used, allowing you to reproduce any dataset:

```json
{
  "seed": 42,
  "generator_version": "1.0.0",
  "generated_at": "2024-01-15T10:30:00+00:00",
  "counts": {
    "users": 50,
    "orders": 200,
    "trades": 500,
    "instruments": 10
  }
}
```

## Contents

| File/Directory | Description | Format | Update Frequency |
|---------------|-------------|--------|-----------------|
| `schema.sql` | Database schema definition | SQL | Per migration |
| `seed.sql` | Seed data for development | SQL | Per release |
| `migration.sql` | Pending database migrations | SQL | Per deployment |
| `reference/` | Reference data (instruments, exchanges) | JSON | Weekly |
| `test/` | Test data for development | JSON | Manual |
| `backup/` | Database backup snapshots | SQL | Daily |

## Schema Files

The `schema.sql` file contains the complete database schema. It is auto-generated
from the migration files and may not reflect the current state of the database
if migrations have been applied manually. For the authoritative schema, query
the `information_schema` tables directly.

## Seed Data

The `seed.sql` file contains seed data for development environments only.
It creates sample users, instruments, and configuration that make the
application usable immediately after deployment.

WARNING: The seed data includes test API keys and passwords that are publicly
visible in this repository. Do NOT use these credentials in production.
The seed data is intended for local development only.

## Migration Files

Migration files follow the naming convention: `{YYYYMMDDHHMMSS}_{description}.sql`
Migration files are applied in order by the migration tool. The migration state
is tracked in the `_migrations` table in the database.

Pending migrations that have not yet been applied to production:
- 20240701000000_add_analytics_rollups.sql (in review)
- 20240715000000_add_user_activity_indexes.sql (in review)

## Backup Files

Database backup snapshots are stored in the `backup/` directory. These are
created by the automated backup system and are retained for 30 days. The
backup files are compressed with gzip and encrypted with GPG.

To restore a backup:
```bash
gpg -d backup/tent_production_20240101.sql.gz | gunzip | psql -h localhost tent_production
```

The GPG key ID is stored in the team vault under `secret/database/backup-key`.
