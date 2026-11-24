"""Extract and aggregate seed metrics for Stage 4."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from aggregate import aggregate_metrics, aggregate_rows
    from metrics_handler import collect_metrics
else:
    from .aggregate import aggregate_metrics, aggregate_rows
    from .metrics_handler import collect_metrics

from utils.dual_graph_handler import load_dual_graph


def _load_manifest(experiment_directory: Path) -> dict[str, Any]:
    manifest_file = experiment_directory / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"Experiment manifest must be an object: {manifest_file}")
    return manifest


def _percentage(penetration: float) -> int:
    return int(round(penetration * 100))


def extract_metrics(
    experiment_name: str,
    penetration: float | None = None,
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    experiment_directory = Path(
        os.environ.get(
            "EXPERIMENT_DIR",
            str(Path(__file__).resolve().parents[3] / "experiments"),
        )
    ).expanduser().resolve() / experiment_name
    manifest = _load_manifest(experiment_directory)

    network_directory = Path(
        os.environ.get(
            "NETWORK_DIR",
            str(experiment_directory.parents[1] / "source files" / "networks"),
        )
    ).expanduser().resolve()
    network_file = network_directory / str(manifest["network"])
    graph_file = experiment_directory / "artifacts" / "graph.graphml"
    subgraph_file = experiment_directory / "artifacts" / "subgraph.graphml"
    for required_file in (network_file, graph_file, subgraph_file):
        if not required_file.is_file():
            raise FileNotFoundError(f"Required artifact not found: {required_file}")

    output_root = experiment_directory / "output"
    metrics_root = experiment_directory / "metrics"
    incident = manifest["incident"]
    penetrations = [0.0] + [
        float(penetration)
        for penetration in manifest["cav_penetrations"]
        if float(penetration) > 0.0
    ]
    if strategy not in (None, "m0", "m1", "m2", "m3"):
        raise ValueError("strategy must be one of m0, m1, m2 or m3")
    if penetration is not None:
        if not 0.0 < penetration <= 1.0:
            raise ValueError("penetration must be greater than 0 and at most 1")
        if not any(abs(penetration - configured) < 1e-9 for configured in penetrations):
            raise ValueError(
                f"Penetration {penetration:g} is not configured in cav_penetrations"
            )
        if strategy == "m0":
            raise ValueError(
                "m0 always uses p0 and does not accept --penetration"
            )
    if strategy == "m0":
        selected_runs = [(0.0, "m0")]
    else:
        selected_penetrations = (
            [penetration]
            if penetration is not None
            else [configured for configured in penetrations if configured > 0.0]
        )
        selected_strategies = [strategy] if strategy is not None else ["m1", "m2", "m3"]
        selected_runs = [
            (selected_penetration, selected_strategy)
            for selected_penetration in selected_penetrations
            for selected_strategy in selected_strategies
        ]
        if strategy is None and penetration is None:
            selected_runs.insert(0, (0.0, "m0"))
    seeds = [int(seed) for seed in manifest["simulation_seeds"]]
    if not seeds:
        raise ValueError("simulation_seeds must contain at least one seed")

    results: list[dict[str, Any]] = []
    graph = load_dual_graph(str(graph_file))
    subgraph = load_dual_graph(str(subgraph_file))

    for selected_penetration, selected_strategy in selected_runs:
        percentage = _percentage(selected_penetration)
        strategy = selected_strategy
        seed_metrics: list[dict[str, Any]] = []
        stability_seed_rows: list[list[dict[str, Any]]] = []
        computation_time_seed_rows: list[list[dict[str, Any]]] = []
        congestion_seed_rows: dict[str, list[list[dict[str, Any]]]] = {}
        aggregate_directory = metrics_root / f"p{percentage}" / strategy
        aggregate_directory.mkdir(parents=True, exist_ok=True)

        for seed in seeds:
            raw_output = (
                output_root
                / f"p{percentage}"
                / strategy
                / f"seed_{seed}"
            )
            if not raw_output.is_dir():
                raise FileNotFoundError(
                    f"Simulation output not found: {raw_output}"
                )
            metrics = collect_metrics(
                incident_edge=str(incident["edge"]),
                output_dir=raw_output,
                incident_start_s=float(incident["begin_s"]),
                incident_end_s=float(incident["end_s"]),
                sim_duration_seconds=float(manifest["end_s"]),
                graph=graph,
                subgraph=subgraph,
                exclude_ids=["veh_bloqueo"],
            )
            seed_metrics.append(metrics)
            stability_seed_rows.append(metrics["stability_timeseries"])
            computation_time_seed_rows.append(metrics["computation_time_timeseries"])
            for zone, rows in metrics["congestion_timeseries"].items():
                congestion_seed_rows.setdefault(str(zone), []).append(rows)

        aggregated = aggregate_metrics(seed_metrics)
        metrics_file = aggregate_directory / "metrics.json"
        metrics_file.write_text(
            json.dumps(aggregated, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        stability_output = aggregate_directory / "metrics_stability_by_step.csv"
        aggregate_rows(
            stability_seed_rows,
            stability_output,
            "time",
        )
        computation_time_output = (
            aggregate_directory / "metrics_computation_time_by_step.csv"
        )
        aggregate_rows(
            computation_time_seed_rows,
            computation_time_output,
            "time",
        )
        timeseries = {
            "stability": str(stability_output),
            "computation_time": str(computation_time_output),
        }

        for zone, seed_rows in congestion_seed_rows.items():
            output_file = (
                aggregate_directory
                / f"metrics_congestion_{zone}_by_interval.csv"
            )
            aggregate_rows(
                seed_rows,
                output_file,
                "interval_midpoint_s",
            )
            timeseries[f"congestion:{zone}"] = str(output_file)

        results.append(
            {
                "penetration": selected_penetration,
                "strategy": strategy,
                "metrics": str(metrics_file),
                "timeseries": timeseries,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract and aggregate Stage 4 metrics"
    )
    parser.add_argument("experiment", help="Experiment name")
    parser.add_argument(
        "--penetration",
        type=float,
        help="CAV penetration rate configured in the manifest",
    )
    parser.add_argument(
        "--strategy",
        choices=("m0", "m1", "m2", "m3"),
    )
    args = parser.parse_args()
    results = extract_metrics(
        args.experiment,
        penetration=args.penetration,
        strategy=args.strategy,
    )
    print(
        f"Aggregated metrics for {len(results)} penetration/strategy combinations"
    )


if __name__ == "__main__":
    main()
