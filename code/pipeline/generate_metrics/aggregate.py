"""Aggregate seed-level metric values for one penetration and strategy."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np


def _aggregate_leaves(samples: list[Any]) -> Any:
    if not samples:
        return {"mean": 0.0, "std": 0.0}
    if all(isinstance(sample, Mapping) for sample in samples):
        keys = set()
        for sample in samples:
            keys.update(sample.keys())
        return {
            key: _aggregate_leaves(
                [sample[key] for sample in samples if key in sample]
            )
            for key in sorted(keys)
        }
    if all(
        isinstance(sample, (int, float)) and not isinstance(sample, bool)
        for sample in samples
    ):
        values = np.asarray(samples, dtype=float)
        return {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "n": len(samples),
            "values": [float(value) for value in values],
        }
    return {"values": samples}


def aggregate_metrics(seed_metrics: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    samples = [
        {
            key: value
            for key, value in metrics.items()
            if not key.endswith("_timeseries")
        }
        for metrics in seed_metrics
    ]
    if not samples:
        raise ValueError("At least one seed metrics file is required")
    return _aggregate_leaves(samples)


def aggregate_rows(
    seed_rows: Iterable[list[Mapping[str, Any]]],
    output_file: Path,
    index_column: str,
) -> Path:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for rows in seed_rows:
        for row in rows:
            if index_column not in row:
                continue
            index = str(row[index_column])
            for column, value in row.items():
                if column == index_column:
                    continue
                try:
                    grouped[index][column].append(float(value))
                except (TypeError, ValueError):
                    continue

    if not grouped:
        return output_file

    numeric_columns = sorted(
        {
            column
            for row_values in grouped.values()
            for column in row_values
        }
    )
    fieldnames = [index_column]
    for column in numeric_columns:
        fieldnames.extend((column, f"{column}_std"))

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in sorted(grouped, key=lambda value: float(value)):
            row: dict[str, Any] = {index_column: index}
            for column in numeric_columns:
                values = grouped[index].get(column)
                if not values:
                    continue
                array = np.asarray(values, dtype=float)
                row[column] = float(np.mean(array))
                row[f"{column}_std"] = float(np.std(array))
            writer.writerow(row)
    return output_file
