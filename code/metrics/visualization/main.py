"""CLI for exporting visualizations from processed experiment metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from metrics.visualization.plots import visualize_metrics


def _resolve_path(value: str | Path, base_directory: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base_directory / path).resolve()


def export_visualizations(config_file: Path) -> list[Path]:
    """Read a visualization config and export all requested figures."""
    config_file = config_file.resolve()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Visualization config must be an object: {config_file}")

    metrics_directory = _resolve_path(
        config["metrics_directory"], config_file.parent
    )
    output_directory = _resolve_path(
        config.get("output_directory", metrics_directory / "visualizations"),
        config_file.parent,
    )
    strategies = config.get("strategies", ["m0"])
    if not isinstance(strategies, list) or not strategies:
        raise ValueError("strategies must be a non-empty list")
    formats = config.get("formats", ["png"])
    if not isinstance(formats, list) or not formats:
        raise ValueError("formats must be a non-empty list")
    plots = config.get("plots", ["summary", "stability", "congestion"])
    if not isinstance(plots, list) or not plots:
        raise ValueError("plots must be a non-empty list")

    return visualize_metrics(
        metrics_directory=metrics_directory,
        output_directory=output_directory,
        strategies=[str(strategy) for strategy in strategies],
        formats=[str(file_format).lower().lstrip(".") for file_format in formats],
        plots=[str(plot) for plot in plots],
        dpi=int(config.get("dpi", 150)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export visualizations from processed experiment metrics"
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    paths = export_visualizations(args.config)
    print(f"Exported {len(paths)} visualization files")


if __name__ == "__main__":
    main()
