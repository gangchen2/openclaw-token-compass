from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from .provider import detect_provider, get_provider_profile
from .tokenizer import estimate_text_tokens


class WorkflowValidationError(ValueError):
    pass


def _as_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _as_str(payload.get(key))
        if value:
            return value
    return ""


def _validate_workflow(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise WorkflowValidationError("workflow must be a JSON object")

    if "project" not in data or not isinstance(data["project"], str) or not data["project"].strip():
        raise WorkflowValidationError("workflow.project is required and must be a non-empty string")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise WorkflowValidationError("workflow.steps is required and must be a non-empty list")

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise WorkflowValidationError(f"workflow.steps[{i}] must be an object")
        for field in ("name", "model", "input_text"):
            if field not in step:
                raise WorkflowValidationError(f"workflow.steps[{i}].{field} is required")
            if not isinstance(step[field], str):
                raise WorkflowValidationError(f"workflow.steps[{i}].{field} must be a string")


def _estimate_output_tokens(step: dict[str, Any], input_tokens: int, default_ratio: float) -> int:
    explicit = step.get("expected_output_tokens")
    if explicit is not None:
        return max(1, int(explicit))

    ratio = step.get("output_token_ratio", default_ratio)
    try:
        ratio_float = float(ratio)
    except Exception:
        ratio_float = float(default_ratio)

    ratio_float = max(0.05, min(1.5, ratio_float))
    return max(1, round(input_tokens * ratio_float))


def estimate_workflow(
    workflow: dict[str, Any],
    *,
    get_multiplier: Callable[[str, str, str], float],
    now: datetime | None = None,
) -> dict[str, Any]:
    _validate_workflow(workflow)

    timestamp = now or datetime.now()
    run_id = f"run_{timestamp.strftime('%Y%m%d_%H%M%S')}"

    workflow_provider = _first_str(workflow, ("provider", "token_provider"))
    workflow_interface = _first_str(workflow, ("api_interface", "interface", "api_type"))
    workflow_api_base = _first_str(workflow, ("api_base", "api_base_url", "base_url"))
    workflow_api_url = _first_str(workflow, ("api_url", "url"))
    workflow_endpoint = _first_str(workflow, ("endpoint", "path"))

    out_steps: list[dict[str, Any]] = []
    total_input = 0
    total_output = 0
    total_base = 0
    total_calibrated = 0
    provider_totals: dict[str, int] = {}

    for idx, step in enumerate(workflow["steps"], start=1):
        name = step["name"].strip()
        model = step["model"].strip()
        input_text = step["input_text"]

        step_provider = _first_str(step, ("provider", "token_provider")) or workflow_provider
        step_interface = _first_str(step, ("api_interface", "interface", "api_type")) or workflow_interface
        step_api_base = _first_str(step, ("api_base", "api_base_url", "base_url")) or workflow_api_base
        step_api_url = _first_str(step, ("api_url", "url")) or workflow_api_url
        step_endpoint = _first_str(step, ("endpoint", "path")) or workflow_endpoint

        provider, provider_source = detect_provider(
            explicit_provider=step_provider,
            api_interface=step_interface,
            api_base=step_api_base,
            api_url=step_api_url,
            endpoint=step_endpoint,
            model=model,
        )
        profile = get_provider_profile(provider)

        input_tokens = estimate_text_tokens(input_text, model, provider=provider)
        output_tokens = _estimate_output_tokens(step, input_tokens, profile.default_output_ratio)
        base_total = input_tokens + output_tokens

        raw_multiplier = get_multiplier(name, model, provider)
        multiplier = max(0.5, min(2.0, float(raw_multiplier)))
        calibrated_total = round(base_total * multiplier)

        total_input += input_tokens
        total_output += output_tokens
        total_base += base_total
        total_calibrated += calibrated_total
        provider_totals[provider] = provider_totals.get(provider, 0) + calibrated_total

        out_steps.append(
            {
                "index": idx,
                "name": name,
                "provider": provider,
                "provider_detection_source": provider_source,
                "model": model,
                "input_tokens_estimate": input_tokens,
                "output_tokens_estimate": output_tokens,
                "base_total_tokens_estimate": base_total,
                "calibration_multiplier": round(multiplier, 4),
                "calibrated_total_tokens_estimate": calibrated_total,
            }
        )

    providers_summary = [
        {
            "provider": provider,
            "calibrated_total_tokens_estimate": total,
        }
        for provider, total in sorted(provider_totals.items(), key=lambda kv: kv[0])
    ]

    return {
        "run_id": run_id,
        "created_at": timestamp.isoformat(timespec="seconds"),
        "project": workflow["project"],
        "provider_summary": providers_summary,
        "totals": {
            "input_tokens_estimate": total_input,
            "output_tokens_estimate": total_output,
            "base_total_tokens_estimate": total_base,
            "calibrated_total_tokens_estimate": total_calibrated,
        },
        "steps": out_steps,
    }
