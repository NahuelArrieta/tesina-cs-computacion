"""Plot and export metrics for one or more experiment strategies."""

from __future__ import annotations

import csv
import base64
import html
import json
import mimetypes
from pathlib import Path
from typing import Any, Iterable, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


MetricData = dict[str, Any]
SUPPORTED_PLOTS = {"summary", "stability", "congestion"}
StageWindows = tuple[float, float] | None


def _available_strategies(metrics_directory: Path) -> list[str]:
    return sorted(
        directory.name
        for directory in metrics_directory.iterdir()
        if directory.is_dir() and (directory / "metrics.json").is_file()
    )


def _read_metrics(
    metrics_directory: Path, strategies: Iterable[str]
) -> dict[str, MetricData]:
    data: dict[str, MetricData] = {}
    for strategy in strategies:
        metrics_file = metrics_directory / strategy / "metrics.json"
        if not metrics_file.is_file():
            raise FileNotFoundError(f"Metrics file not found: {metrics_file}")
        value = json.loads(metrics_file.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"Metrics file must contain an object: {metrics_file}")
        data[strategy] = value
    return data


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Time-series file not found: {path}")
    with path.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def _draw_stage_boundaries(axis: plt.Axes, incident_window: StageWindows) -> None:
    if incident_window is None:
        return
    incident_start_s, incident_end_s = incident_window
    x_min, x_max = axis.get_xlim()
    axis.axvspan(
        x_min,
        incident_start_s,
        color="#4c78a8",
        alpha=0.10,
        label="Pre-incident",
        zorder=0,
    )
    axis.axvspan(
        incident_start_s,
        incident_end_s,
        color="#e45756",
        alpha=0.12,
        label="Incident",
        zorder=0,
    )
    axis.axvspan(
        incident_end_s,
        x_max,
        color="#59a14f",
        alpha=0.10,
        label="Post-incident",
        zorder=0,
    )
    axis.axvline(incident_start_s, color="#b22222", linestyle="--", linewidth=1.2)
    axis.axvline(incident_end_s, color="#b22222", linestyle="--", linewidth=1.2)


def _save_figure(
    figure: plt.Figure,
    output_directory: Path,
    stem: str,
    formats: Iterable[str],
    dpi: int,
) -> list[Path]:
    paths = []
    for file_format in formats:
        if file_format not in {"png", "svg", "pdf"}:
            raise ValueError(f"Unsupported output format: {file_format}")
        path = output_directory / f"{stem}.{file_format}"
        figure.savefig(path, dpi=dpi, bbox_inches="tight")
        paths.append(path)
    plt.close(figure)
    return paths


def _write_report(output_directory: Path, paths: Iterable[Path]) -> Path:
    plot_paths: dict[str, dict[str, Path]] = {}
    for path in paths:
        suffix = path.suffix.lower().lstrip(".")
        if suffix in {"png", "svg", "pdf"}:
            plot_paths.setdefault(path.stem, {})[suffix] = path

    sections = []
    for stem, variants in plot_paths.items():
        title = html.escape(stem.replace("_", " ").title())
        embedded_format = next(
            (file_format for file_format in ("png", "svg") if file_format in variants),
            None,
        )
        if embedded_format is None:
            sections.append(f"<h2>{title}</h2>")
        else:
            path = variants[embedded_format]
            content = base64.b64encode(path.read_bytes()).decode("ascii")
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            sections.append(
                f"<h2>{title}</h2>"
                f'<img src="data:{mime_type};base64,{content}" '
                f'alt="{title}" />'
            )

        links = [
            f'<a href="{html.escape(path.name)}">{html.escape(file_format.upper())}</a>'
            for file_format, path in sorted(variants.items())
            if file_format == "pdf"
        ]
        if links:
            sections.append("<p>Downloads: " + " | ".join(links) + "</p>")
    report_path = output_directory / "report.html"
    report_path.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>Metrics visualizations</title>"
        "<style>body{font-family:sans-serif;max-width:1200px;margin:auto}"
        "img{display:block;max-width:100%;margin-bottom:2rem}</style>"
        "</head><body><h1>Metrics visualizations</h1>"
        + "".join(sections)
        + "</body></html>\n",
        encoding="utf-8",
    )
    return report_path


def _plot_summary(
    data: Mapping[str, MetricData],
    output_directory: Path,
    formats: Iterable[str],
    dpi: int,
) -> list[Path]:
    efficiency_keys = (
        "mean_travel_time_s",
        "mean_delay_s",
        "mean_speed_mps",
        "throughput_veh_hour",
    )
    strategies = list(data)
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for axis, key in zip(axes.flat, efficiency_keys):
        values = [
            float(data[strategy].get("efficiency", {}).get(key, 0.0))
            for strategy in strategies
        ]
        axis.bar(strategies, values)
        axis.set_title(key.replace("_", " ").title())
        axis.grid(axis="y", alpha=0.25)
        axis.set_axisbelow(True)
    figure.suptitle("Efficiency comparison")
    return _save_figure(figure, output_directory, "efficiency_comparison", formats, dpi)


def _plot_stability(
    metrics_directory: Path,
    strategies: Iterable[str],
    output_directory: Path,
    formats: Iterable[str],
    dpi: int,
    incident_window: StageWindows,
) -> list[Path]:
    figure, axis = plt.subplots(figsize=(11, 6), constrained_layout=True)
    for strategy in strategies:
        rows = _read_csv(metrics_directory / strategy / "metrics_stability_by_step.csv")
        axis.plot(
            [float(row["time"]) for row in rows],
            [float(row["mean_speed_mps"]) for row in rows],
            label=strategy,
        )
    _draw_stage_boundaries(axis, incident_window)
    axis.set_title("Mean speed over time")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Mean speed (m/s)")
    axis.grid(alpha=0.25)
    axis.legend()
    return _save_figure(figure, output_directory, "stability_mean_speed", formats, dpi)


def _plot_congestion(
    metrics_directory: Path,
    strategies: Iterable[str],
    data: Mapping[str, MetricData],
    output_directory: Path,
    formats: Iterable[str],
    dpi: int,
    incident_window: StageWindows,
) -> list[Path]:
    zones = sorted(
        {
            zone
            for strategy in strategies
            for zone in data[strategy].get("congestion", {})
        }
    )
    paths: list[Path] = []
    for zone in zones:
        figure, axis = plt.subplots(figsize=(11, 6), constrained_layout=True)
        for strategy in strategies:
            rows = _read_csv(
                metrics_directory
                / strategy
                / f"metrics_congestion_{zone}_by_interval.csv"
            )
            axis.plot(
                [float(row["interval_midpoint_s"]) for row in rows],
                [float(row["mean_queue_length_m"]) for row in rows],
                label=strategy,
            )
        _draw_stage_boundaries(axis, incident_window)
        axis.set_title(f"Mean queue length: {zone.replace('_', ' ').title()}")
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Queue length (m)")
        axis.grid(alpha=0.25)
        axis.legend()
        paths.extend(
            _save_figure(
                figure, output_directory, f"congestion_{zone}", formats, dpi
            )
        )
    return paths


def visualize_metrics(
    metrics_directory: str | Path,
    output_directory: str | Path,
    strategies: Iterable[str] | None = None,
    formats: Iterable[str] = ("png",),
    plots: Iterable[str] = ("summary", "stability", "congestion"),
    dpi: int = 150,
    incident_window: StageWindows = None,
) -> list[Path]:
    """Export selected figures for all requested strategies.

    The strategy directories must contain the files generated by
    :func:`metrics.metrics_handler.export_metrics`.
    """
    metrics_path = Path(metrics_directory)
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    strategy_list = (
        _available_strategies(metrics_path)
        if strategies is None
        else list(strategies)
    )
    plot_list = list(plots)
    unknown_plots = set(plot_list).difference(SUPPORTED_PLOTS)
    if unknown_plots:
        raise ValueError(f"Unsupported plots: {sorted(unknown_plots)}")
    if not strategy_list:
        raise ValueError("strategies must be a non-empty iterable")
    format_list = list(formats)
    if not format_list:
        raise ValueError("formats must be a non-empty iterable")
    data = _read_metrics(metrics_path, strategy_list)
    paths: list[Path] = []
    if "summary" in plot_list:
        paths.extend(_plot_summary(data, output_path, format_list, dpi))
    if "stability" in plot_list:
        paths.extend(
            _plot_stability(
                metrics_path,
                strategy_list,
                output_path,
                format_list,
                dpi,
                incident_window,
            )
        )
    if "congestion" in plot_list:
        paths.extend(
            _plot_congestion(
                metrics_path,
                strategy_list,
                data,
                output_path,
                format_list,
                dpi,
                incident_window,
            )
        )

    report_path = _write_report(output_path, paths)
    manifest = {
        "metrics_directory": str(metrics_path.resolve()),
        "strategies": strategy_list,
        "plots": plot_list,
        "files": [str(path) for path in paths],
        "report": str(report_path),
        "incident_window": incident_window,
    }
    manifest_path = output_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    paths.append(manifest_path)
    paths.append(report_path)
    return paths
