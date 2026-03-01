from __future__ import annotations

import json

from openclaw_token_compass.log_parser import extract_actual_payload


def test_extract_actual_from_json_events(tmp_path):
    payload = {
        "run_id": "run_abc",
        "project": "p1",
        "events": [
            {
                "step": "implementation",
                "model": "gpt-4o",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 60,
                    "total_tokens": 160,
                },
            },
            {
                "step": "implementation",
                "model": "gpt-4o",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 70,
                    "total_tokens": 190,
                },
            },
            {
                "step_name": "summary",
                "model": "gpt-4o-mini",
                "actual_input_tokens": 50,
                "actual_output_tokens": 25,
                "actual_total_tokens": 75,
            },
        ],
    }
    log_path = tmp_path / "run.json"
    log_path.write_text(json.dumps(payload), encoding="utf-8")

    actual = extract_actual_payload(str(log_path))

    assert actual["run_id"] == "run_abc"
    assert actual["project"] == "p1"
    assert actual["provider"] == "openai"
    assert len(actual["steps"]) == 2

    by_name = {row["name"]: row for row in actual["steps"]}
    impl = by_name["implementation"]
    assert impl["provider"] == "openai"
    assert impl["actual_input_tokens"] == 220
    assert impl["actual_output_tokens"] == 130
    assert impl["actual_total_tokens"] == 350


def test_extract_actual_from_plain_text_lines(tmp_path):
    lines = [
        "step=requirements_analysis model=gpt-4o-mini prompt_tokens=200 completion_tokens=80 total_tokens=280",
        "step=requirements_analysis model=gpt-4o-mini prompt_tokens=100 completion_tokens=40 total_tokens=140",
        "step=summary model=gpt-4o-mini prompt_tokens=60 completion_tokens=30",
    ]
    log_path = tmp_path / "run.log"
    log_path.write_text("\n".join(lines), encoding="utf-8")

    actual = extract_actual_payload(str(log_path), run_id="run_x", project="demo")

    assert actual["run_id"] == "run_x"
    assert actual["project"] == "demo"
    assert actual["provider"] == "openai"
    assert len(actual["steps"]) == 2

    by_name = {row["name"]: row for row in actual["steps"]}
    req = by_name["requirements_analysis"]
    assert req["provider"] == "openai"
    assert req["actual_input_tokens"] == 300
    assert req["actual_output_tokens"] == 120
    assert req["actual_total_tokens"] == 420

    summary = by_name["summary"]
    assert summary["actual_input_tokens"] == 60
    assert summary["actual_output_tokens"] == 30
    assert summary["actual_total_tokens"] == 90


def test_extract_actual_detects_provider_from_api_url(tmp_path):
    payload = {
        "run_id": "run_api",
        "project": "p2",
        "api_base": "https://api.anthropic.com/v1/messages",
        "events": [
            {
                "step": "analysis",
                "model": "custom-model",
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "total_tokens": 70,
            }
        ],
    }
    log_path = tmp_path / "run_api.json"
    log_path.write_text(json.dumps(payload), encoding="utf-8")

    actual = extract_actual_payload(str(log_path))

    assert actual["provider"] == "anthropic"
    assert actual["steps"][0]["provider"] == "anthropic"
