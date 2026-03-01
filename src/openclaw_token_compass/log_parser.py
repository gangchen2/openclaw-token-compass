from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .provider import detect_provider

_STEP_KEYS = ("step_name", "step", "name", "task", "phase")
_MODEL_KEYS = ("model", "model_name", "model_id")
_PROVIDER_KEYS = ("provider", "token_provider", "vendor")
_INTERFACE_KEYS = ("api_interface", "interface", "api_type")
_API_BASE_KEYS = ("api_base", "api_base_url", "base_url")
_API_URL_KEYS = ("api_url", "url")
_ENDPOINT_KEYS = ("endpoint", "path")
_INPUT_KEYS = (
    "actual_input_tokens",
    "input_tokens",
    "prompt_tokens",
    "prompt_token_count",
)
_OUTPUT_KEYS = (
    "actual_output_tokens",
    "output_tokens",
    "completion_tokens",
    "completion_token_count",
)
_TOTAL_KEYS = ("actual_total_tokens", "total_tokens", "total_token_count")
_CONTAINER_KEYS = ("steps", "events", "records", "items")


@dataclass
class ParsedEvent:
    step_name: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class LogParseError(ValueError):
    pass


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def _pick_str(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _pick_int(record: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key in record:
            parsed = _to_int(record.get(key))
            if parsed is not None:
                return parsed
    return None


def _extract_dict(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _normalize_event(
    record: dict[str, Any],
    *,
    default_model: str,
    default_provider: str,
    default_interface: str,
    default_api_base: str,
    default_api_url: str,
    default_endpoint: str,
) -> ParsedEvent | None:
    usage = _extract_dict(record, "usage")
    metrics = _extract_dict(record, "metrics")
    request = _extract_dict(record, "request")

    step_name = (
        _pick_str(record, _STEP_KEYS)
        or _pick_str(usage, _STEP_KEYS)
        or _pick_str(metrics, _STEP_KEYS)
        or _pick_str(request, _STEP_KEYS)
        or "unknown_step"
    )
    model = (
        _pick_str(record, _MODEL_KEYS)
        or _pick_str(usage, _MODEL_KEYS)
        or _pick_str(metrics, _MODEL_KEYS)
        or _pick_str(request, _MODEL_KEYS)
        or default_model
    )
    explicit_provider = (
        _pick_str(record, _PROVIDER_KEYS)
        or _pick_str(usage, _PROVIDER_KEYS)
        or _pick_str(metrics, _PROVIDER_KEYS)
        or _pick_str(request, _PROVIDER_KEYS)
        or default_provider
    )
    api_interface = (
        _pick_str(record, _INTERFACE_KEYS)
        or _pick_str(usage, _INTERFACE_KEYS)
        or _pick_str(metrics, _INTERFACE_KEYS)
        or _pick_str(request, _INTERFACE_KEYS)
        or default_interface
    )
    api_base = (
        _pick_str(record, _API_BASE_KEYS)
        or _pick_str(usage, _API_BASE_KEYS)
        or _pick_str(metrics, _API_BASE_KEYS)
        or _pick_str(request, _API_BASE_KEYS)
        or default_api_base
    )
    api_url = (
        _pick_str(record, _API_URL_KEYS)
        or _pick_str(usage, _API_URL_KEYS)
        or _pick_str(metrics, _API_URL_KEYS)
        or _pick_str(request, _API_URL_KEYS)
        or default_api_url
    )
    endpoint = (
        _pick_str(record, _ENDPOINT_KEYS)
        or _pick_str(usage, _ENDPOINT_KEYS)
        or _pick_str(metrics, _ENDPOINT_KEYS)
        or _pick_str(request, _ENDPOINT_KEYS)
        or default_endpoint
    )

    input_tokens = _pick_int(record, _INPUT_KEYS)
    if input_tokens is None:
        input_tokens = _pick_int(usage, _INPUT_KEYS) or _pick_int(metrics, _INPUT_KEYS)

    output_tokens = _pick_int(record, _OUTPUT_KEYS)
    if output_tokens is None:
        output_tokens = _pick_int(usage, _OUTPUT_KEYS) or _pick_int(metrics, _OUTPUT_KEYS)

    total_tokens = _pick_int(record, _TOTAL_KEYS)
    if total_tokens is None:
        total_tokens = _pick_int(usage, _TOTAL_KEYS) or _pick_int(metrics, _TOTAL_KEYS)

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None

    provider, _source = detect_provider(
        explicit_provider=explicit_provider,
        api_interface=api_interface,
        api_base=api_base,
        api_url=api_url,
        endpoint=endpoint,
        model=model,
    )

    resolved_input = input_tokens or 0
    resolved_output = output_tokens or 0
    resolved_total = total_tokens if total_tokens is not None else (resolved_input + resolved_output)

    return ParsedEvent(
        step_name=step_name,
        provider=provider,
        model=model,
        input_tokens=resolved_input,
        output_tokens=resolved_output,
        total_tokens=resolved_total,
    )


def _extract_records_from_json(data: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if isinstance(data, list):
        records = [item for item in data if isinstance(item, dict)]
        return records, {}

    if not isinstance(data, dict):
        return [], {}

    metadata = {
        "run_id": data.get("run_id") if isinstance(data.get("run_id"), str) else "",
        "project": data.get("project") if isinstance(data.get("project"), str) else "",
        "provider": _pick_str(data, _PROVIDER_KEYS) or "",
        "api_interface": _pick_str(data, _INTERFACE_KEYS) or "",
        "api_base": _pick_str(data, _API_BASE_KEYS) or "",
        "api_url": _pick_str(data, _API_URL_KEYS) or "",
        "endpoint": _pick_str(data, _ENDPOINT_KEYS) or "",
    }

    for key in _CONTAINER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            records = [item for item in value if isinstance(item, dict)]
            return records, metadata

    return [data], metadata


def _line_value(line: str, key: str, numeric: bool) -> str | int | None:
    if numeric:
        match = re.search(rf"\b{re.escape(key)}\s*[:=]\s*(\d+)", line, re.IGNORECASE)
        return int(match.group(1)) if match else None

    quoted = re.search(rf"\b{re.escape(key)}\s*[:=]\s*[\"']([^\"']+)[\"']", line, re.IGNORECASE)
    if quoted:
        return quoted.group(1).strip()

    plain = re.search(rf"\b{re.escape(key)}\s*[:=]\s*([^\s,]+)", line, re.IGNORECASE)
    if plain:
        return plain.group(1).strip()
    return None


def _parse_text_line(
    line: str,
    *,
    default_model: str,
    default_provider: str,
    default_interface: str,
    default_api_base: str,
    default_api_url: str,
    default_endpoint: str,
) -> ParsedEvent | None:
    text = line.strip()
    if not text:
        return None

    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return _normalize_event(
                parsed,
                default_model=default_model,
                default_provider=default_provider,
                default_interface=default_interface,
                default_api_base=default_api_base,
                default_api_url=default_api_url,
                default_endpoint=default_endpoint,
            )

    step_name: str | None = None
    for key in _STEP_KEYS:
        value = _line_value(text, key, numeric=False)
        if isinstance(value, str):
            step_name = value
            break

    model: str | None = None
    for key in _MODEL_KEYS:
        value = _line_value(text, key, numeric=False)
        if isinstance(value, str):
            model = value
            break

    explicit_provider: str | None = None
    for key in _PROVIDER_KEYS:
        value = _line_value(text, key, numeric=False)
        if isinstance(value, str):
            explicit_provider = value
            break

    api_interface: str | None = None
    for key in _INTERFACE_KEYS:
        value = _line_value(text, key, numeric=False)
        if isinstance(value, str):
            api_interface = value
            break

    api_base: str | None = None
    for key in _API_BASE_KEYS:
        value = _line_value(text, key, numeric=False)
        if isinstance(value, str):
            api_base = value
            break

    api_url: str | None = None
    for key in _API_URL_KEYS:
        value = _line_value(text, key, numeric=False)
        if isinstance(value, str):
            api_url = value
            break

    endpoint: str | None = None
    for key in _ENDPOINT_KEYS:
        value = _line_value(text, key, numeric=False)
        if isinstance(value, str):
            endpoint = value
            break

    input_tokens: int | None = None
    for key in _INPUT_KEYS:
        value = _line_value(text, key, numeric=True)
        if isinstance(value, int):
            input_tokens = value
            break

    output_tokens: int | None = None
    for key in _OUTPUT_KEYS:
        value = _line_value(text, key, numeric=True)
        if isinstance(value, int):
            output_tokens = value
            break

    total_tokens: int | None = None
    for key in _TOTAL_KEYS:
        value = _line_value(text, key, numeric=True)
        if isinstance(value, int):
            total_tokens = value
            break

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None

    resolved_model = model or default_model
    provider, _source = detect_provider(
        explicit_provider=explicit_provider or default_provider,
        api_interface=api_interface or default_interface,
        api_base=api_base or default_api_base,
        api_url=api_url or default_api_url,
        endpoint=endpoint or default_endpoint,
        model=resolved_model,
    )

    resolved_input = input_tokens or 0
    resolved_output = output_tokens or 0
    resolved_total = total_tokens if total_tokens is not None else (resolved_input + resolved_output)

    return ParsedEvent(
        step_name=(step_name or "unknown_step"),
        provider=provider,
        model=resolved_model,
        input_tokens=resolved_input,
        output_tokens=resolved_output,
        total_tokens=resolved_total,
    )


def _aggregate(events: list[ParsedEvent]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in events:
        key = (event.step_name, event.provider, event.model)
        if key not in grouped:
            grouped[key] = {
                "name": event.step_name,
                "provider": event.provider,
                "model": event.model,
                "actual_input_tokens": 0,
                "actual_output_tokens": 0,
                "actual_total_tokens": 0,
            }

        row = grouped[key]
        row["actual_input_tokens"] += event.input_tokens
        row["actual_output_tokens"] += event.output_tokens
        row["actual_total_tokens"] += event.total_tokens

    return list(grouped.values())


def extract_actual_payload(
    log_path: str,
    *,
    run_id: str | None = None,
    project: str | None = None,
    default_model: str = "unknown_model",
    default_provider: str | None = None,
) -> dict[str, Any]:
    path = Path(log_path)
    if not path.exists():
        raise LogParseError(f"log file not found: {log_path}")

    content = path.read_text(encoding="utf-8", errors="ignore")

    metadata: dict[str, str] = {}
    events: list[ParsedEvent] = []

    parsed_json: Any | None = None
    try:
        parsed_json = json.loads(content)
    except Exception:
        parsed_json = None

    if parsed_json is not None:
        records, metadata = _extract_records_from_json(parsed_json)
    else:
        records = []

    resolved_default_provider, _source = detect_provider(
        explicit_provider=default_provider or metadata.get("provider"),
        api_interface=metadata.get("api_interface"),
        api_base=metadata.get("api_base"),
        api_url=metadata.get("api_url"),
        endpoint=metadata.get("endpoint"),
        model=default_model,
    )
    resolved_default_interface = metadata.get("api_interface") or ""
    resolved_default_api_base = metadata.get("api_base") or ""
    resolved_default_api_url = metadata.get("api_url") or ""
    resolved_default_endpoint = metadata.get("endpoint") or ""

    if parsed_json is not None:
        for record in records:
            event = _normalize_event(
                record,
                default_model=default_model,
                default_provider=resolved_default_provider,
                default_interface=resolved_default_interface,
                default_api_base=resolved_default_api_base,
                default_api_url=resolved_default_api_url,
                default_endpoint=resolved_default_endpoint,
            )
            if event is not None:
                events.append(event)
    else:
        for line in content.splitlines():
            event = _parse_text_line(
                line,
                default_model=default_model,
                default_provider=resolved_default_provider,
                default_interface=resolved_default_interface,
                default_api_base=resolved_default_api_base,
                default_api_url=resolved_default_api_url,
                default_endpoint=resolved_default_endpoint,
            )
            if event is not None:
                events.append(event)

    if not events:
        raise LogParseError(
            "no token usage data found in log; ensure each record has input/output/total tokens"
        )

    resolved_run_id = run_id or metadata.get("run_id") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    resolved_project = project or metadata.get("project") or "unknown_project"

    providers = {event.provider for event in events}
    run_provider = next(iter(providers)) if len(providers) == 1 else "mixed"

    return {
        "run_id": resolved_run_id,
        "project": resolved_project,
        "provider": run_provider,
        "steps": _aggregate(events),
    }
