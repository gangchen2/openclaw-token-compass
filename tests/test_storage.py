from __future__ import annotations

from datetime import datetime

from openclaw_token_compass.storage import (
    calibration_stats,
    get_calibration_multiplier,
    init_db,
    record_observation,
)


def test_calibration_multiplier_step_model_provider(tmp_path):
    db = tmp_path / "forecast.db"
    init_db(str(db))

    now = datetime.now().isoformat(timespec="seconds")
    for _ in range(3):
        record_observation(
            str(db),
            recorded_at=now,
            run_id="run1",
            project="p",
            step_name="implementation",
            provider="openai",
            model="gpt-4o",
            estimated_total_tokens=100,
            actual_input_tokens=70,
            actual_output_tokens=50,
            actual_total_tokens=120,
        )

    ratio = get_calibration_multiplier(
        str(db),
        step_name="implementation",
        model="gpt-4o",
        provider="openai",
    )
    assert abs(ratio - 1.2) < 1e-6


def test_calibration_multiplier_isolated_by_provider(tmp_path):
    db = tmp_path / "forecast.db"
    init_db(str(db))

    now = datetime.now().isoformat(timespec="seconds")
    for _ in range(3):
        record_observation(
            str(db),
            recorded_at=now,
            run_id="run_openai",
            project="p",
            step_name="implementation",
            provider="openai",
            model="gpt-4o",
            estimated_total_tokens=100,
            actual_input_tokens=70,
            actual_output_tokens=50,
            actual_total_tokens=120,
        )
    for _ in range(3):
        record_observation(
            str(db),
            recorded_at=now,
            run_id="run_anthropic",
            project="p",
            step_name="implementation",
            provider="anthropic",
            model="gpt-4o",
            estimated_total_tokens=100,
            actual_input_tokens=40,
            actual_output_tokens=40,
            actual_total_tokens=80,
        )

    openai_ratio = get_calibration_multiplier(
        str(db),
        step_name="implementation",
        model="gpt-4o",
        provider="openai",
    )
    anthropic_ratio = get_calibration_multiplier(
        str(db),
        step_name="implementation",
        model="gpt-4o",
        provider="anthropic",
    )

    assert abs(openai_ratio - 1.2) < 1e-6
    assert abs(anthropic_ratio - 0.8) < 1e-6


def test_calibration_stats_rows(tmp_path):
    db = tmp_path / "forecast.db"
    init_db(str(db))
    now = datetime.now().isoformat(timespec="seconds")

    record_observation(
        str(db),
        recorded_at=now,
        run_id="run2",
        project="p",
        step_name="summary",
        provider="openai",
        model="gpt-4o-mini",
        estimated_total_tokens=200,
        actual_input_tokens=120,
        actual_output_tokens=90,
        actual_total_tokens=210,
    )

    rows = calibration_stats(str(db))
    assert len(rows) == 1
    assert rows[0]["step_name"] == "summary"
    assert rows[0]["provider"] == "openai"
    assert rows[0]["model"] == "gpt-4o-mini"
