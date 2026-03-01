# OpenClaw Token Compass

Provider-aware token estimation and calibration toolkit for OpenClaw workflows.

OpenClaw Token Compass estimates token usage before a run, records real usage after completion, and continuously improves estimation accuracy through historical calibration. It supports mixed-provider workflows and can auto-detect provider hints from API interface, endpoint URL, model names, and environment variables.

## Suggested GitHub Repository Description

Provider-aware token estimator for OpenClaw with post-run calibration and continuous accuracy improvement.

## Core Capabilities

- Workflow-level estimation with per-step breakdown
- Provider-aware estimation profiles (`OpenAI`, `Azure OpenAI`, `Anthropic`, `Google Gemini`, etc.)
- Automatic provider detection priority: `explicit provider > api_interface > api_url/api_base > model > env`
- Post-run ingestion of actual token usage
- Calibration by `step + model + provider` with fallback hierarchy
- Error reporting after each run (`actual vs estimated` + error percentage)
- Continuous-learning message to encourage ongoing usage and data feedback

## Installation

```bash
cd /Users/chengang/Documents/New\ project/openclaw-token-compass
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

CLI commands after install:

- `openclaw-token-compass` (new primary command)
- `openclaw-token` (backward-compatible alias)

## Use As An OpenClaw Plugin

This repository includes a ready-to-install bridge plugin in [`openclaw-plugin`](./openclaw-plugin).

One-step install:

```bash
cd /Users/chengang/Documents/New\ project/openclaw-token-compass
./scripts/install_openclaw_plugin.sh
```

Manual install:

```bash
openclaw plugins install -l /Users/chengang/Documents/New\ project/openclaw-token-compass/openclaw-plugin
openclaw plugins enable token-compass
openclaw plugins info token-compass
```

Recommended environment variables:

```bash
export TOKEN_COMPASS_BIN="/Users/chengang/Documents/New project/.venv/bin/openclaw-token-compass"
export TOKEN_COMPASS_DB="/Users/chengang/Documents/New project/openclaw-token-compass/data/token_forecast.db"
```

Registered plugin tools:

- `token_compass_estimate`
- `token_compass_extract_actual`
- `token_compass_record`
- `token_compass_stats`

## Quick Start

### 1) Initialize database

```bash
openclaw-token-compass init-db --db ./data/token_forecast.db
```

### 2) Estimate before execution

```bash
openclaw-token-compass estimate \
  --workflow ./examples/workflow.sample.json \
  --db ./data/token_forecast.db \
  --out ./examples/estimate.output.json
```

If your workflow file does not include provider hints, you can override:

```bash
openclaw-token-compass estimate \
  --workflow ./examples/workflow.sample.json \
  --provider openai \
  --db ./data/token_forecast.db
```

### 3) Record actual usage after execution

```bash
openclaw-token-compass record \
  --actual ./examples/actual.sample.json \
  --estimate ./examples/estimate.output.json \
  --db ./data/token_forecast.db
```

Output includes:

- Error formula: `(actual - estimated) / estimated * 100%`
- Run-level error percentage
- Step-level error percentages
- Continuous-learning guidance: accuracy improves as more data is collected

### 4) Extract actual usage from OpenClaw logs (recommended)

```bash
openclaw-token-compass extract-actual \
  --log ./examples/openclaw.log \
  --out ./examples/actual.from_log.json \
  --run-id run_20260301_170000 \
  --project openclaw_demo_project
```

Then ingest:

```bash
openclaw-token-compass record \
  --actual ./examples/actual.from_log.json \
  --estimate ./examples/estimate.output.json \
  --db ./data/token_forecast.db
```

If provider metadata is missing in the log, override it:

```bash
openclaw-token-compass extract-actual \
  --log ./examples/openclaw.log \
  --out ./examples/actual.from_log.json \
  --provider anthropic
```

### 5) View calibration stats

```bash
openclaw-token-compass stats --db ./data/token_forecast.db
```

## JSON Examples

### Workflow

```json
{
  "project": "my-openclaw-task",
  "api_interface": "openai",
  "api_base": "https://api.openai.com/v1",
  "steps": [
    {
      "name": "requirements_analysis",
      "model": "gpt-4o-mini",
      "input_text": "...",
      "expected_output_tokens": 300
    },
    {
      "name": "implementation",
      "api_interface": "anthropic",
      "api_base": "https://api.anthropic.com/v1/messages",
      "model": "claude-3-5-sonnet",
      "input_text": "...",
      "output_token_ratio": 0.45
    }
  ]
}
```

### Actual

```json
{
  "run_id": "run_20260301_120000",
  "project": "my-openclaw-task",
  "provider": "mixed",
  "steps": [
    {
      "name": "requirements_analysis",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "actual_input_tokens": 800,
      "actual_output_tokens": 260,
      "actual_total_tokens": 1060
    }
  ]
}
```

## Notes

- Uses `tiktoken` when available; applies provider-specific adjustments for non-OpenAI providers.
- Calibration uses recent samples (default: 200) with provider-aware precedence.
- `extract-actual` supports `JSON`, `JSONL`, and `key=value` text logs.
