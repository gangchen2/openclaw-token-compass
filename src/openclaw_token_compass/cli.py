from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .estimator import WorkflowValidationError, estimate_workflow
from .log_parser import LogParseError, extract_actual_payload
from .provider import detect_provider
from .storage import calibration_stats, get_calibration_multiplier, init_db, record_observation


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON in {path} must be an object")
    return data


def _save_json(path: str, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _error_percent(estimated: int, actual: int) -> float | None:
    if estimated <= 0:
        return None
    return ((actual - estimated) / estimated) * 100.0


def _pick_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _cmd_init_db(args: argparse.Namespace) -> int:
    init_db(args.db)
    print(f"DB initialized: {args.db}")
    return 0


def _cmd_estimate(args: argparse.Namespace) -> int:
    init_db(args.db)
    workflow = _load_json(args.workflow)

    provider_override = getattr(args, "provider", None)
    workflow_provider = _pick_string(workflow, ("provider", "token_provider")).lower()
    if provider_override and workflow_provider in {"", "unknown", "mixed"}:
        workflow["provider"] = provider_override

    def _multiplier(step_name: str, model: str, provider: str) -> float:
        return get_calibration_multiplier(
            args.db,
            step_name=step_name,
            model=model,
            provider=provider,
        )

    try:
        result = estimate_workflow(workflow, get_multiplier=_multiplier)
    except WorkflowValidationError as exc:
        print(f"workflow validation error: {exc}")
        return 2

    print("提示：以下 token 仅为预估值，实际消耗会有误差。")
    print("提示：系统会自动识别 provider 并使用对应估算模型（接口/URL/模型/环境变量）。")
    print(f"Run ID: {result['run_id']}")
    print(f"Project: {result['project']}")
    print("Step Estimates:")
    print("-" * 124)
    print(
        f"{'#':<3} {'step':<24} {'provider':<12} {'model':<16} {'input':>8} {'output':>8} {'base':>8} {'x':>6} {'final':>8} {'src':<10}"
    )
    print("-" * 124)
    for step in result["steps"]:
        print(
            f"{step['index']:<3} "
            f"{step['name'][:24]:<24} "
            f"{step['provider'][:12]:<12} "
            f"{step['model'][:16]:<16} "
            f"{step['input_tokens_estimate']:>8} "
            f"{step['output_tokens_estimate']:>8} "
            f"{step['base_total_tokens_estimate']:>8} "
            f"{step['calibration_multiplier']:>6.2f} "
            f"{step['calibrated_total_tokens_estimate']:>8} "
            f"{step['provider_detection_source'][:10]:<10}"
        )
    print("-" * 124)
    totals = result["totals"]
    print(
        "Totals: "
        f"input={totals['input_tokens_estimate']} "
        f"output={totals['output_tokens_estimate']} "
        f"base={totals['base_total_tokens_estimate']} "
        f"final={totals['calibrated_total_tokens_estimate']}"
    )
    providers = ", ".join(
        f"{row['provider']}={row['calibrated_total_tokens_estimate']}"
        for row in result.get("provider_summary", [])
    )
    if providers:
        print(f"Provider Totals: {providers}")

    if args.out:
        _save_json(args.out, result)
        print(f"Saved estimate: {args.out}")

    return 0


def _estimate_maps(estimate_payload: dict[str, Any]) -> tuple[dict[tuple[str, str, str], int], dict[tuple[str, str], int]]:
    exact: dict[tuple[str, str, str], int] = {}
    fallback: dict[tuple[str, str], int] = {}
    for step in estimate_payload.get("steps", []):
        if not isinstance(step, dict):
            continue

        name = str(step.get("name", "")).strip()
        model = str(step.get("model", "")).strip()
        est = step.get("calibrated_total_tokens_estimate")
        if not name or not model or est is None:
            continue

        provider, _ = detect_provider(
            explicit_provider=str(step.get("provider", "")).strip() or None,
            model=model,
        )
        exact[(name, model, provider)] = int(est)
        fallback[(name, model)] = int(est)
    return exact, fallback


def _cmd_record(args: argparse.Namespace) -> int:
    init_db(args.db)
    actual_payload = _load_json(args.actual)
    estimate_payload = _load_json(args.estimate) if args.estimate else {}
    exact_lookup, fallback_lookup = _estimate_maps(estimate_payload)

    run_id = str(actual_payload.get("run_id") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    project = str(actual_payload.get("project") or "unknown_project")
    steps = actual_payload.get("steps")
    if not isinstance(steps, list) or not steps:
        print("actual.steps is required and must be a non-empty list")
        return 2

    provider_override = getattr(args, "provider", None)
    payload_provider = provider_override or _pick_string(actual_payload, ("provider", "token_provider"))
    payload_interface = _pick_string(actual_payload, ("api_interface", "interface", "api_type"))
    payload_api_base = _pick_string(actual_payload, ("api_base", "api_base_url", "base_url"))
    payload_api_url = _pick_string(actual_payload, ("api_url", "url"))
    payload_endpoint = _pick_string(actual_payload, ("endpoint", "path"))

    now = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    run_estimated = 0
    run_actual = 0
    error_rows: list[tuple[str, str, str, int, int, float]] = []
    skipped_error_steps = 0
    for item in steps:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        model = str(item.get("model", "")).strip()
        if not name or not model:
            continue

        provider, _provider_source = detect_provider(
            explicit_provider=_pick_string(item, ("provider", "token_provider")) or payload_provider,
            api_interface=_pick_string(item, ("api_interface", "interface", "api_type")) or payload_interface,
            api_base=_pick_string(item, ("api_base", "api_base_url", "base_url")) or payload_api_base,
            api_url=_pick_string(item, ("api_url", "url")) or payload_api_url,
            endpoint=_pick_string(item, ("endpoint", "path")) or payload_endpoint,
            model=model,
        )

        actual_input = int(item.get("actual_input_tokens", 0))
        actual_output = int(item.get("actual_output_tokens", 0))
        actual_total = int(item.get("actual_total_tokens", actual_input + actual_output))

        est_from_payload = item.get("estimated_total_tokens")
        if est_from_payload is not None:
            estimated_total = int(est_from_payload)
        else:
            estimated_total = exact_lookup.get((name, model, provider))
            if estimated_total is None:
                estimated_total = fallback_lookup.get((name, model), 0)

        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        record_observation(
            args.db,
            recorded_at=now,
            run_id=run_id,
            project=project,
            step_name=name,
            provider=provider,
            model=model,
            estimated_total_tokens=estimated_total,
            actual_input_tokens=actual_input,
            actual_output_tokens=actual_output,
            actual_total_tokens=actual_total,
            metadata=metadata,
        )
        inserted += 1

        step_error = _error_percent(estimated_total, actual_total)
        if step_error is None:
            skipped_error_steps += 1
            continue

        run_estimated += estimated_total
        run_actual += actual_total
        error_rows.append((name, provider, model, estimated_total, actual_total, step_error))

    print(f"Recorded observations: {inserted} (run_id={run_id}, project={project})")
    print("提示：误差百分比公式 = (实际 - 估计) / 估计 * 100%")
    if error_rows:
        run_error = _error_percent(run_estimated, run_actual)
        run_error_text = f"{run_error:+.2f}%" if run_error is not None else "N/A"
        print(
            "任务结束误差汇总: "
            f"estimated={run_estimated} actual={run_actual} error={run_error_text}"
        )
        print(
            f"{'step':<24} {'provider':<12} {'model':<16} {'estimated':>10} {'actual':>10} {'error%':>9}"
        )
        print("-" * 88)
        for name, provider, model, estimated_total, actual_total, step_error in error_rows:
            print(
                f"{name[:24]:<24} "
                f"{provider[:12]:<12} "
                f"{model[:16]:<16} "
                f"{estimated_total:>10} "
                f"{actual_total:>10} "
                f"{step_error:>+8.2f}%"
            )
    else:
        print("任务结束误差汇总: 无法计算（缺少 estimated_total_tokens）。")

    if skipped_error_steps > 0:
        print(f"跳过 {skipped_error_steps} 个步骤：这些步骤没有可用的估计值。")
    print("提示：随着样本数据持续增加，估算准确率会不断提高，请继续使用并回传真实 token 数据。")
    return 0


def _cmd_extract_actual(args: argparse.Namespace) -> int:
    try:
        payload = extract_actual_payload(
            args.log,
            run_id=args.run_id,
            project=args.project,
            default_model=getattr(args, "default_model", "unknown_model"),
            default_provider=getattr(args, "provider", None),
        )
    except LogParseError as exc:
        print(f"log parse error: {exc}")
        return 2

    _save_json(args.out, payload)

    print(f"Saved actual usage: {args.out}")
    print(f"Run ID: {payload['run_id']}")
    print(f"Project: {payload['project']}")
    print(f"Provider: {payload.get('provider', 'unknown')}")
    print(f"{'step':<24} {'provider':<12} {'model':<16} {'input':>8} {'output':>8} {'total':>8}")
    print("-" * 94)
    sum_input = 0
    sum_output = 0
    sum_total = 0
    for step in payload["steps"]:
        sum_input += int(step["actual_input_tokens"])
        sum_output += int(step["actual_output_tokens"])
        sum_total += int(step["actual_total_tokens"])
        print(
            f"{step['name'][:24]:<24} "
            f"{step['provider'][:12]:<12} "
            f"{step['model'][:16]:<16} "
            f"{step['actual_input_tokens']:>8} "
            f"{step['actual_output_tokens']:>8} "
            f"{step['actual_total_tokens']:>8}"
        )
    print("-" * 94)
    print(f"Totals: input={sum_input} output={sum_output} total={sum_total}")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    init_db(args.db)
    rows = calibration_stats(args.db)
    if not rows:
        print("No calibration samples yet.")
        return 0

    print(
        f"{'step':<24} {'provider':<12} {'model':<16} {'samples':>8} {'avg_est':>10} {'avg_act':>10} {'ratio':>8} {'x':>8}"
    )
    print("-" * 110)
    for row in rows:
        print(
            f"{row['step_name'][:24]:<24} "
            f"{row['provider'][:12]:<12} "
            f"{row['model'][:16]:<16} "
            f"{row['samples']:>8} "
            f"{row['avg_estimated']:>10.1f} "
            f"{row['avg_actual']:>10.1f} "
            f"{row['avg_ratio']:>8.3f} "
            f"{row['suggested_multiplier']:>8.3f}"
        )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw token forecasting and calibration CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init_parser = sub.add_parser("init-db", help="Initialize SQLite database")
    init_parser.add_argument("--db", required=True, help="SQLite path")
    init_parser.set_defaults(func=_cmd_init_db)

    estimate_parser = sub.add_parser("estimate", help="Estimate token usage before running workflow")
    estimate_parser.add_argument("--workflow", required=True, help="Workflow JSON path")
    estimate_parser.add_argument("--db", required=True, help="SQLite path")
    estimate_parser.add_argument("--provider", help="Override provider when workflow does not specify it")
    estimate_parser.add_argument("--out", help="Write estimate result to JSON path")
    estimate_parser.set_defaults(func=_cmd_estimate)

    record_parser = sub.add_parser("record", help="Record actual token usage after run")
    record_parser.add_argument("--actual", required=True, help="Actual usage JSON path")
    record_parser.add_argument("--estimate", help="Estimate JSON path (optional)")
    record_parser.add_argument("--provider", help="Override provider when actual payload does not include it")
    record_parser.add_argument("--db", required=True, help="SQLite path")
    record_parser.set_defaults(func=_cmd_record)

    extract_parser = sub.add_parser("extract-actual", help="Extract actual token usage from OpenClaw logs")
    extract_parser.add_argument("--log", required=True, help="Log file path (JSON, JSONL, or plain text)")
    extract_parser.add_argument("--out", required=True, help="Output actual usage JSON path")
    extract_parser.add_argument("--run-id", help="Override run_id in generated actual payload")
    extract_parser.add_argument("--project", help="Override project in generated actual payload")
    extract_parser.add_argument("--provider", help="Override detected provider for this log")
    extract_parser.add_argument(
        "--default-model",
        default="unknown_model",
        help="Fallback model name when missing in log records",
    )
    extract_parser.set_defaults(func=_cmd_extract_actual)

    stats_parser = sub.add_parser("stats", help="Show calibration statistics")
    stats_parser.add_argument("--db", required=True, help="SQLite path")
    stats_parser.set_defaults(func=_cmd_stats)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
