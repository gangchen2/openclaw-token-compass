from __future__ import annotations

from datetime import datetime

from openclaw_token_compass.estimator import estimate_workflow


def test_estimate_workflow_applies_multiplier():
    workflow = {
        "project": "demo",
        "steps": [
            {
                "name": "step1",
                "model": "gpt-4o-mini",
                "input_text": "hello world",
                "expected_output_tokens": 50,
            }
        ],
    }

    result = estimate_workflow(
        workflow,
        get_multiplier=lambda _step, _model, _provider: 1.5,
        now=datetime(2026, 3, 1, 15, 0, 0),
    )

    assert result["run_id"] == "run_20260301_150000"
    step = result["steps"][0]
    assert step["provider"] == "openai"
    assert step["base_total_tokens_estimate"] == step["input_tokens_estimate"] + 50
    assert step["calibrated_total_tokens_estimate"] == round(step["base_total_tokens_estimate"] * 1.5)


def test_estimate_workflow_detects_provider_from_interface():
    workflow = {
        "project": "demo",
        "api_interface": "anthropic",
        "steps": [
            {
                "name": "analysis",
                "model": "model-not-prefixed",
                "input_text": "a" * 120,
            }
        ],
    }

    result = estimate_workflow(
        workflow,
        get_multiplier=lambda _step, _model, _provider: 1.0,
        now=datetime(2026, 3, 1, 15, 1, 0),
    )

    step = result["steps"][0]
    assert step["provider"] == "anthropic"
    assert step["provider_detection_source"] == "api_interface"
