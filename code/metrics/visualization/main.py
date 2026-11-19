"""CLI for exporting visualizations from processed experiment metrics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from metrics.visualization.plots import visualize_metrics



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
        sim_duration_s=float(manifest["end_s"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Stage 5 experiment report")
    parser.add_argument("experiment", help="Experiment name")
    args = parser.parse_args()
    paths = export_visualizations(args.experiment)
    print(f"Exported {len(paths)} visualization files")


if __name__ == "__main__":
    main()
