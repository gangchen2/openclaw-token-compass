from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    run_id TEXT NOT NULL,
    project TEXT NOT NULL,
    step_name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown',
    model TEXT NOT NULL,
    estimated_total_tokens INTEGER NOT NULL,
    actual_input_tokens INTEGER NOT NULL,
    actual_output_tokens INTEGER NOT NULL,
    actual_total_tokens INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
"""


INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_observations_step_model_provider
ON observations(step_name, model, provider);

CREATE INDEX IF NOT EXISTS idx_observations_model_provider
ON observations(model, provider);

CREATE INDEX IF NOT EXISTS idx_observations_step_model
ON observations(step_name, model);

CREATE INDEX IF NOT EXISTS idx_observations_model
ON observations(model);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_provider_column(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(observations)").fetchall()
    column_names = {str(row["name"]) for row in columns}
    if "provider" not in column_names:
        conn.execute("ALTER TABLE observations ADD COLUMN provider TEXT NOT NULL DEFAULT 'unknown'")


def init_db(db_path: str) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_provider_column(conn)
        conn.executescript(INDEX_SQL)
        conn.commit()


def record_observation(
    db_path: str,
    *,
    recorded_at: str,
    run_id: str,
    project: str,
    step_name: str,
    provider: str,
    model: str,
    estimated_total_tokens: int,
    actual_input_tokens: int,
    actual_output_tokens: int,
    actual_total_tokens: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = json.dumps(metadata or {}, ensure_ascii=True)
    with _connect(db_path) as conn:
        _ensure_provider_column(conn)
        conn.execute(
            """
            INSERT INTO observations (
                recorded_at,
                run_id,
                project,
                step_name,
                provider,
                model,
                estimated_total_tokens,
                actual_input_tokens,
                actual_output_tokens,
                actual_total_tokens,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recorded_at,
                run_id,
                project,
                step_name,
                provider,
                model,
                int(estimated_total_tokens),
                int(actual_input_tokens),
                int(actual_output_tokens),
                int(actual_total_tokens),
                payload,
            ),
        )
        conn.commit()


def _mean_ratio_for_query(conn: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> tuple[float, int]:
    rows = conn.execute(query, params).fetchall()
    if not rows:
        return 1.0, 0
    ratios = [float(r["ratio"]) for r in rows if r["ratio"] is not None]
    if not ratios:
        return 1.0, 0
    return sum(ratios) / len(ratios), len(ratios)


def _clamp_multiplier(value: float, low: float = 0.5, high: float = 2.0) -> float:
    return max(low, min(high, value))


def get_calibration_multiplier(
    db_path: str,
    *,
    step_name: str,
    model: str,
    provider: str,
    min_samples: int = 3,
    lookback: int = 200,
) -> float:
    with _connect(db_path) as conn:
        _ensure_provider_column(conn)

        step_provider_query = """
            SELECT (actual_total_tokens * 1.0 / NULLIF(estimated_total_tokens, 0)) AS ratio
            FROM observations
            WHERE step_name = ? AND model = ? AND provider = ? AND estimated_total_tokens > 0
            ORDER BY id DESC
            LIMIT ?
        """
        step_provider_avg, step_provider_count = _mean_ratio_for_query(
            conn,
            step_provider_query,
            (step_name, model, provider, lookback),
        )
        if step_provider_count >= min_samples:
            return _clamp_multiplier(step_provider_avg)

        model_provider_query = """
            SELECT (actual_total_tokens * 1.0 / NULLIF(estimated_total_tokens, 0)) AS ratio
            FROM observations
            WHERE model = ? AND provider = ? AND estimated_total_tokens > 0
            ORDER BY id DESC
            LIMIT ?
        """
        model_provider_avg, model_provider_count = _mean_ratio_for_query(
            conn,
            model_provider_query,
            (model, provider, lookback),
        )
        if model_provider_count >= min_samples:
            return _clamp_multiplier(model_provider_avg)

        step_query = """
            SELECT (actual_total_tokens * 1.0 / NULLIF(estimated_total_tokens, 0)) AS ratio
            FROM observations
            WHERE step_name = ? AND model = ? AND estimated_total_tokens > 0
            ORDER BY id DESC
            LIMIT ?
        """
        step_avg, step_count = _mean_ratio_for_query(conn, step_query, (step_name, model, lookback))
        if step_count >= min_samples:
            return _clamp_multiplier(step_avg)

        model_query = """
            SELECT (actual_total_tokens * 1.0 / NULLIF(estimated_total_tokens, 0)) AS ratio
            FROM observations
            WHERE model = ? AND estimated_total_tokens > 0
            ORDER BY id DESC
            LIMIT ?
        """
        model_avg, model_count = _mean_ratio_for_query(conn, model_query, (model, lookback))
        if model_count >= min_samples:
            return _clamp_multiplier(model_avg)

    return 1.0


def calibration_stats(db_path: str) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        _ensure_provider_column(conn)
        rows = conn.execute(
            """
            SELECT
                step_name,
                provider,
                model,
                COUNT(*) AS samples,
                AVG(estimated_total_tokens) AS avg_estimated,
                AVG(actual_total_tokens) AS avg_actual,
                AVG(actual_total_tokens * 1.0 / NULLIF(estimated_total_tokens, 0)) AS avg_ratio
            FROM observations
            WHERE estimated_total_tokens > 0
            GROUP BY step_name, provider, model
            ORDER BY samples DESC, step_name ASC, provider ASC, model ASC
            """
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "step_name": row["step_name"],
                "provider": row["provider"],
                "model": row["model"],
                "samples": int(row["samples"]),
                "avg_estimated": float(row["avg_estimated"]),
                "avg_actual": float(row["avg_actual"]),
                "avg_ratio": float(row["avg_ratio"]),
                "suggested_multiplier": _clamp_multiplier(float(row["avg_ratio"])),
            }
        )
    return result
