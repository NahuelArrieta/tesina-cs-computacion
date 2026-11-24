import csv
import os
from pathlib import Path
from typing import Any

import numpy as np


def parse_computation_time(csv_file_path: str | Path) -> list[dict[str, float]]:
    if not os.path.exists(csv_file_path):
        raise FileNotFoundError(f"File not found: {csv_file_path}")

    records: list[dict[str, float]] = []
    with open(csv_file_path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            records.append(
                {
                    "time": float(row["time"]),
                    "execution_time_s": float(row["execution_time_s"]),
                }
            )
    return records


def compute_computation_time_metrics(
    records: list[dict[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not records:
        return [], {
            "steps": 0,
            "total_time_s": 0.0,
            "mean_step_time_ms": 0.0,
            "std_step_time_ms": 0.0,
            "p95_step_time_ms": 0.0,
            "max_step_time_ms": 0.0,
        }

    times_s = np.asarray([record["execution_time_s"] for record in records], dtype=float)
    times_ms = times_s * 1000.0

    step_summary = [
        {
            "time": record["time"],
            "execution_time_ms": round(record["execution_time_s"] * 1000.0, 6),
        }
        for record in records
    ]

    summary = {
        "steps": int(len(records)),
        "total_time_s": round(float(np.sum(times_s)), 6),
        "mean_step_time_ms": round(float(np.mean(times_ms)), 4),
        "std_step_time_ms": round(float(np.std(times_ms)), 4),
        "p95_step_time_ms": round(float(np.percentile(times_ms, 95)), 4),
        "max_step_time_ms": round(float(np.max(times_ms)), 4),
    }
    return step_summary, summary


def parse_and_compute_computation_time(
    csv_file_path: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = parse_computation_time(csv_file_path)
    return compute_computation_time_metrics(records)
