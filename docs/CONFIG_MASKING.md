# Config Generator Secret Masking

The config generator (`tools/config_generator.py`) automatically masks sensitive
values in all output formats (YAML, JSON, TOML, dotenv, Kubernetes ConfigMap).

## Masking Rules

Any config key whose name (case-insensitive) contains one of these substrings
is redacted:

| Pattern      | Examples                                              |
|--------------|-------------------------------------------------------|
| `TOKEN`      | `jwt_token`, `access_token`, `refresh_token`          |
| `SECRET`     | `jwt_secret`, `client_secret`, `api_secret`           |
| `KEY`        | `api_key`, `signing_key`, `encryption_key`            |
| `PASSWORD`   | `password`, `db_password`, `admin_password`           |
| `CREDENTIAL` | `credentials`, `aws_credential`, `service_credential` |

When a key matches, its value is replaced with `***REDACTED***` in all output
formats. This applies to:

- Top-level dictionary values
- Nested dictionary values (recursive)
- List items that are dictionaries containing sensitive keys
- Flattened dotenv and Kubernetes ConfigMap keys

## Non-secret values

Keys that do not match the patterns above are preserved unmasked, including
`host`, `port`, `name`, `timeout_ms`, `pool_size`, `debug`, `log_level`, etc.
This preserves useful diagnostic information while hiding actual secrets.

## Override

Use `--show-sensitive` to disable masking and output raw values:

```
python3 tools/config_generator.py --env production --format yaml --show-sensitive
```

## Testing

Run the masking tests:

```
python3 -m pytest tests/test_config_generator.py -v
```
