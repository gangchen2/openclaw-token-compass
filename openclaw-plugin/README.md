# OpenClaw Token Compass Plugin (Bridge)

This plugin exposes `openclaw-token-compass` CLI as OpenClaw tools.

## Tools

- `token_compass_estimate`
- `token_compass_extract_actual`
- `token_compass_record`
- `token_compass_stats`

## Config

You can configure the plugin using either environment variables or plugin config:

- `TOKEN_COMPASS_BIN` or `binPath`: absolute path to `openclaw-token-compass`
- `TOKEN_COMPASS_DB` or `dbPath`: absolute path to SQLite db

Priority:
1. Environment variable
2. Plugin config
3. Auto-detected local `.venv` path
4. `openclaw-token-compass` in PATH

## Install

```bash
openclaw plugins install -l /absolute/path/to/openclaw-plugin
openclaw plugins enable token-compass
```

## Verify

```bash
openclaw plugins info token-compass
openclaw plugins doctor
```
