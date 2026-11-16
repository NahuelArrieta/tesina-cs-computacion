"""Run one experiment strategy and export its metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from metrics.metrics_handler import process_metrics
from simulation.simulator import run_from_manifest


def run_experiment(manifest_file: Path, strategy: str) -> None:
    """Run a strategy from an experiment manifest and process its outputs."""
    manifest_file = manifest_file.resolve()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    output_directory = Path(manifest["output_directory"]).resolve() / strategy
    experiment_directory = Path(manifest["experiment_directory"]).resolve()
    metrics_directory = experiment_directory / "metrics" / strategy
    incident = manifest["incident"]
    simulation = manifest["simulation"]

    run_from_manifest(manifest_file, strategy)
    process_metrics(
        incident_edge=str(incident["edge"]),
        output_dir=output_directory,
        incident_start_s=float(incident["begin_s"]),
        incident_end_s=float(incident["end_s"]),
        sim_duration_seconds=float(simulation["end_s"]),
        export_dir=metrics_directory,
        name="",
        graph_file=manifest["graph"],
        subgraph_file=manifest["subgraph"],
        exclude_ids=["veh_bloqueo"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one experiment strategy and export its metrics"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--strategy",
        required=True,
        choices=("m0", "m1", "m2", "m3"),
    )
    args = parser.parse_args()
    run_experiment(args.manifest, args.strategy)
    print(f"Completed strategy {args.strategy}")


if __name__ == "__main__":
    main()
