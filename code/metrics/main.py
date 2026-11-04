"""Extract and process metrics from the raw outputs of an experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metrics.metrics_handler import process_metrics


def _read_manifest(manifest_file: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"Experiment manifest must be an object: {manifest_file}")
    return manifest


def _resolve_path(value: str | Path, base_directory: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base_directory / path).resolve()


def extract_metrics(config_file: Path) -> list[dict[str, Any]]:
    """Process every configured strategy from one experiment manifest."""
    config_file = config_file.resolve()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    manifest_file = _resolve_path(config["manifest"], config_file.parent)
    manifest = _read_manifest(manifest_file)

    experiment_directory = _resolve_path(
        manifest.get("experiment_directory", manifest_file.parent),
        manifest_file.parent,
    )
    output_root = _resolve_path(
        manifest.get("output_directory", experiment_directory / "output"),
        manifest_file.parent,
    )
    metrics_root = _resolve_path(
        config.get("metrics_directory", experiment_directory / "metrics"),
        config_file.parent,
    )
    strategies = config.get("strategies", ["m0", "m1", "m2", "m3"])
    if not isinstance(strategies, list) or not strategies:
        raise ValueError("strategies must be a non-empty list")

    incident = manifest["incident"]
    simulation = manifest["simulation"]
    results: list[dict[str, Any]] = []
    for strategy in strategies:
        strategy_name = str(strategy)
        raw_output = output_root / strategy_name
        metric_output = metrics_root / strategy_name
        metrics, paths = process_metrics(
            incident_edge=str(incident["edge"]),
            output_dir=raw_output,
            incident_start_s=float(incident["begin_s"]),
            incident_end_s=float(incident["end_s"]),
            sim_duration_seconds=float(simulation["end_s"]),
            export_dir=metric_output,
            name="",
            graph_file=_resolve_path(manifest["graph"], manifest_file.parent),
            subgraph_file=_resolve_path(manifest["subgraph"], manifest_file.parent),
            exclude_ids=config.get("exclude_ids", []),
            congested_queue_threshold_m=float(
                config.get("congested_queue_threshold_m", 20.0)
            ),
            baseline_speed_ratio=float(config.get("baseline_speed_ratio", 0.90)),
        )
        results.append(
            {
                "strategy": strategy_name,
                "metrics": str(paths["json"]),
                "timeseries": {
                    key: str(path)
                    for key, path in paths.items()
                    if key != "json"
                },
                "values": metrics,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract metrics from raw SUMO experiment outputs"
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    results = extract_metrics(args.config)
    print(f"Extracted metrics for {len(results)} strategies")


if __name__ == "__main__":
    main()
