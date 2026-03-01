from __future__ import annotations

import json
from argparse import Namespace

from openclaw_token_compass.cli import _cmd_record


def test_record_prints_error_percentage(tmp_path, capsys):
    db_path = tmp_path / "forecast.db"

    estimate_payload = {
        "steps": [
            {
                "name": "implementation",
                "model": "gpt-4o",
                "calibrated_total_tokens_estimate": 100,
            }
        ]
    }
    actual_payload = {
        "run_id": "run_test",
        "project": "demo",
        "steps": [
            {
                "name": "implementation",
                "model": "gpt-4o",
                "actual_input_tokens": 70,
                "actual_output_tokens": 50,
                "actual_total_tokens": 120,
            }
        ],
    }

    estimate_path = tmp_path / "estimate.json"
    actual_path = tmp_path / "actual.json"
    estimate_path.write_text(json.dumps(estimate_payload), encoding="utf-8")
    actual_path.write_text(json.dumps(actual_payload), encoding="utf-8")

    args = Namespace(actual=str(actual_path), estimate=str(estimate_path), db=str(db_path))
    code = _cmd_record(args)

    out = capsys.readouterr().out
    assert code == 0
    assert "任务结束误差汇总" in out
    assert "error=+20.00%" in out
    assert "准确率会不断提高，请继续使用" in out
