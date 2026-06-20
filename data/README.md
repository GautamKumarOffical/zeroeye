# Data Directory

This directory contains data files used by the Tent of Trials platform.

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

## Data Manifest

The data generator (`tools/data_generator.py`) supports writing a JSON manifest
that records checksums and metadata for generated output files. This is useful
for verifying data integrity across environments.

### Usage

Generate data and write a manifest:
```bash
python3 tools/data_generator.py --output-dir ./test_data --seed 42 --manifest ./manifest.json
```

Verify output files against a previously written manifest:
```bash
python3 tools/data_generator.py --verify-manifest ./manifest.json
```

### Manifest Schema

```json
{
  "schema_version": 1,
  "generator": "data_generator.py",
  "created_at_seed": "<hex-hash-derived-from-seed>",
  "cli_args": ["data_generator.py", "--seed", "42", ...],
  "seed": 42,
  "output_dir": "/absolute/path/to/output",
  "files": {
    "users.json": {
      "record_count": 50,
      "sha256": "<hex-encoded SHA-256 digest>",
      "size_bytes": 12345
    },
    "orders.json": { ... },
    "trades.json": { ... },
    "ticks.json": { ... },
    "candles.json": { ... },
    "instruments.json": { ... }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Manifest schema version (currently `1`) |
| `generator` | string | Name of the generator script |
| `created_at_seed` | string | Deterministic timestamp derived from the seed |
| `cli_args` | list[string] | Command-line arguments used to generate the data |
| `seed` | int | Random seed used for generation |
| `output_dir` | string | Absolute path to the output directory |
| `files` | object | Map of relative file paths to their metadata |
| `files.*.record_count` | int | Number of records written to the file |
| `files.*.sha256` | string | SHA-256 hex digest of the file contents |
| `files.*.size_bytes` | int | File size in bytes |

The manifest output is deterministic: running the generator with the same
arguments produces identical checksums.
