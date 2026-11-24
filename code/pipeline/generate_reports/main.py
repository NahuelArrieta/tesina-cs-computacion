"""CLI for exporting visualizations from processed experiment metrics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from plots import visualize_metrics
else:
    from .plots import visualize_metrics


CONGESTION_ZONES = (
    "incident_street",
    "upstream_streets",
    "alternative_routes",
    "other_zones",
)


def validate_aggregated_metrics(
    manifest: dict[str, object],
    metrics_directory: Path,
) -> None:
    """Ensure every manifest-defined combination has complete Stage 4 files."""
    configured = [
        float(penetration)
        for penetration in manifest["cav_penetrations"]
    ]
    penetrations = [0.0] + [
        penetration
        for penetration in configured
        if penetration > 0.0
    ]
    missing: list[str] = []

    for penetration in penetrations:
        percentage = int(round(penetration * 100))
        strategies = ["m0"] if percentage == 0 else ["m1", "m2", "m3"]
        for strategy in strategies:
            directory = metrics_directory / f"p{percentage}" / strategy
            required_files = [
                directory / "metrics.json",
                directory / "metrics_stability_by_step.csv",
                directory / "metrics_computation_time_by_step.csv",
            ]
            required_files.extend(
                directory / f"metrics_congestion_{zone}_by_interval.csv"
                for zone in CONGESTION_ZONES
            )
            for required_file in required_files:
                if not required_file.is_file():
                    missing.append(str(required_file))
                    continue
                if required_file.suffix == ".json":
                    json.loads(required_file.read_text(encoding="utf-8"))

    if missing:
        lines = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(
            "Stage 5 found incomplete Stage 4 results. Missing files:\n"
            f"{lines}"
        )


def export_visualizations(experiment_name: str) -> list[Path]:
    """Generate Stage 5 visualizations for one experiment."""
    experiment_directory = Path(
        os.environ.get(
            "EXPERIMENT_DIR",
            str(Path(__file__).resolve().parents[3] / "experiments"),
        )
    ).expanduser().resolve() / experiment_name
    metrics_directory = experiment_directory / "metrics"
    output_directory = experiment_directory / "results" / "graphics"
    manifest_file = experiment_directory / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    validate_aggregated_metrics(manifest, metrics_directory)
    incident = manifest["incident"]
    incident_window = (
        float(incident["begin_s"]),
        float(incident["end_s"]),
    )
    return visualize_metrics(
        metrics_directory=metrics_directory,
        output_directory=output_directory,
        formats=["svg"],
        dpi=150,
        incident_window=incident_window,
        manifest=manifest,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Stage 5 experiment report")
    parser.add_argument("experiment", help="Experiment name")
    args = parser.parse_args()
    paths = export_visualizations(args.experiment)
    print(f"Exported {len(paths)} visualization files")


if __name__ == "__main__":
    main()
