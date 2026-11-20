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
        if file_format != "svg":
            raise ValueError(f"Unsupported output format: {file_format}")
        path = output_directory / f"{stem}.{file_format}"
        figure.savefig(path, dpi=dpi, bbox_inches="tight")
        paths.append(path)
    plt.close(figure)
    return paths


def _write_report(
    output_directory: Path,
    paths: Iterable[Path],
    manifest: Mapping[str, Any] | None = None,
) -> Path:
    plot_paths: dict[str, dict[str, Path]] = {}
    for path in paths:
        suffix = path.suffix.lower().lstrip(".")
        if suffix == "svg":
            plot_paths.setdefault(path.stem, {})[suffix] = path

    sections = []
    for stem, variants in plot_paths.items():
        title = html.escape(stem.replace("_", " ").title())
        if "svg" not in variants:
            sections.append(f"<h2>{title}</h2>")
        else:
            path = variants["svg"]
            content = base64.b64encode(path.read_bytes()).decode("ascii")
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            sections.append(
                f"<h2>{title}</h2>"
                f'<img src="data:{mime_type};base64,{content}" '
                f'alt="{title}" />'
            )
    manifest_section = ""
    if manifest is not None:
        description = html.escape(str(manifest.get("description", "")))
        manifest_json = html.escape(
            json.dumps(manifest, indent=2, ensure_ascii=False)
        )
        manifest_section = (
            "<section><h2>Experiment data</h2>"
            f"<p><strong>Description:</strong> {description}</p>"
            "<details><summary>Manifest JSON</summary>"
            f"<pre>{manifest_json}</pre>"
            "</details></section>"
        )
    report_path = output_directory.parent / "report.html"
    report_path.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>Metrics visualizations</title>"
        "<style>body{font-family:sans-serif;max-width:1200px;margin:auto}"
        "img{display:block;max-width:100%;margin-bottom:2rem}"
        "pre{background:#f5f5f5;padding:1rem;overflow:auto}</style>"
        "</head><body><h1>Metrics visualizations</h1>"
        + manifest_section
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


def _read_aggregated(metrics_directory: Path) -> dict[tuple[int, str], MetricData]:
    data: dict[tuple[int, str], MetricData] = {}
    for penetration_directory in sorted(
        metrics_directory.glob("p*"),
        key=lambda path: int(path.name[1:]),
    ):
        penetration = int(penetration_directory.name[1:])
        for strategy_directory in penetration_directory.iterdir():
            if not strategy_directory.is_dir():
                continue
            metrics_file = strategy_directory / "metrics.json"
            if not metrics_file.is_file():
                continue
            data[(penetration, strategy_directory.name)] = json.loads(
                metrics_file.read_text(encoding="utf-8")
            )
    return data


def _aggregate_value(value: Any) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return float(value.get("mean", 0.0)), float(value.get("std", 0.0))
    return float(value), 0.0


def _flatten_aggregate(
    value: Any,
    prefix: str = "",
) -> dict[str, tuple[float, float]]:
    rows: dict[str, tuple[float, float]] = {}
    if isinstance(value, Mapping):
        if "mean" in value or "n" in value:
            rows[prefix] = _aggregate_value(value)
            return rows
        for key, nested in sorted(value.items()):
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            rows.update(_flatten_aggregate(nested, nested_prefix))
    return rows


def _seed_values(
    metrics_directory: Path,
    penetration: int,
    strategy: str,
) -> list[dict[str, Any]]:
    metrics_file = (
        metrics_directory / f"p{penetration}" / strategy / "metrics.json"
    )
    if not metrics_file.is_file():
        return []
    return [json.loads(metrics_file.read_text(encoding="utf-8"))]


def _plot_scalar_by_penetration(
    data: Mapping[tuple[int, str], MetricData],
    section: str,
    leaf_path: tuple[str, ...],
    title: str,
    ylabel: str,
    output_directory: Path,
    formats: Iterable[str],
    dpi: int,
) -> list[Path]:
    penetrations = sorted({penetration for penetration, _ in data})
    figure, axis = plt.subplots(figsize=(10, 6), constrained_layout=True)
    for strategy in ("m1", "m2", "m3"):
        xs, ys, errors = [], [], []
        for penetration in penetrations:
            value = data.get((penetration, strategy))
            if value is None:
                continue
            current = value
            try:
                for key in (section, *leaf_path):
                    current = current[key]
            except (KeyError, TypeError):
                continue
            mean, std = _aggregate_value(current)
            xs.append(penetration)
            ys.append(mean)
            errors.append(std)
        if xs:
            axis.errorbar(xs, ys, yerr=errors, marker="o", capsize=4, label=strategy.upper())
    baseline = data.get((penetrations[0], "m0"))
    if baseline is not None:
        current = baseline
        try:
            for key in (section, *leaf_path):
                current = current[key]
            mean, _ = _aggregate_value(current)
            axis.axhline(mean, color="#444", linestyle=":", label="M0")
        except (KeyError, TypeError):
            pass
    if not xs and not axis.lines:
        plt.close(figure)
        return []
    axis.set_title(title)
    axis.set_xlabel("CAV penetration (%)")
    axis.set_ylabel(ylabel)
    axis.set_xticks(penetrations)
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    return _save_figure(
        figure,
        output_directory,
        f"{section}_{'_'.join(leaf_path)}",
        formats,
        dpi,
    )


def _plot_seed_boxplots(
    metrics_directory: Path,
    data: Mapping[tuple[int, str], MetricData],
    section: str,
    leaf_path: tuple[str, ...],
    title: str,
    output_directory: Path,
    formats: Iterable[str],
    dpi: int,
) -> list[Path]:
    paths = []
    penetrations = sorted({penetration for penetration, _ in data if penetration > 0})
    for penetration in penetrations:
        box_data = []
        labels = []
        for strategy in ("m0", "m1", "m2", "m3"):
            if (penetration, strategy) not in data:
                continue
            seed_values = []
            for seed in _seed_values(metrics_directory, penetration, strategy):
                current = seed
                try:
                    for key in (section, *leaf_path):
                        current = current[key]
                    samples = current.get("values") if isinstance(current, Mapping) else None
                    if isinstance(samples, list):
                        seed_values.extend(float(value) for value in samples)
                except (KeyError, TypeError, ValueError):
                    continue
            if seed_values:
                box_data.append(seed_values)
                labels.append(strategy.upper())
        if not box_data:
            continue
        figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
        axis.boxplot(box_data, tick_labels=labels)
        axis.set_title(f"{title}: {penetration}% CAV")
        axis.set_xlabel("Strategy")
        axis.grid(axis="y", alpha=0.25)
        paths.extend(
            _save_figure(
                figure,
                output_directory,
                f"boxplot_{section}_{'_'.join(leaf_path)}_p{penetration}",
                formats,
                dpi,
            )
        )
    return paths


def _plot_timeseries(
    metrics_directory: Path,
    metric_name: str,
    title: str,
    output_directory: Path,
    formats: Iterable[str],
    dpi: int,
    incident_window: StageWindows,
    filename_prefix: str,
) -> list[Path]:
    paths = []
    penetrations = sorted(
        int(path.name[1:])
        for path in metrics_directory.glob("p*")
    )
    for penetration in penetrations:
        figure, axis = plt.subplots(figsize=(11, 6), constrained_layout=True)
        for strategy in ("m0", "m1", "m2", "m3"):
            csv_file = (
                metrics_directory
                / f"p{penetration}"
                / strategy
                / f"{filename_prefix}.csv"
            )
            if not csv_file.is_file():
                continue
            rows = _read_csv(csv_file)
            if not rows:
                continue
            index_column = (
                "time"
                if "time" in rows[0]
                else "interval_midpoint_s"
            )
            mean_column = metric_name
            std_column = f"{metric_name}_std"
            xs = [float(row[index_column]) for row in rows]
            ys = [float(row[mean_column]) for row in rows if mean_column in row]
            if len(ys) != len(xs):
                continue
            stds = [
                float(row.get(std_column, 0.0))
                for row in rows
            ]
            axis.plot(xs, ys, label=strategy.upper())
            axis.fill_between(
                xs,
                [value - error for value, error in zip(ys, stds)],
                [value + error for value, error in zip(ys, stds)],
                alpha=0.15,
            )
        _draw_stage_boundaries(axis, incident_window)
        axis.set_title(f"{title}: {penetration}% CAV")
        axis.set_xlabel("Time (s)")
        axis.set_ylabel(metric_name.replace("_", " "))
        axis.grid(alpha=0.25)
        axis.legend()
        paths.extend(
            _save_figure(
                figure,
                output_directory,
                f"{filename_prefix}_p{penetration}",
                formats,
                dpi,
            )
        )
    return paths


def visualize_metrics(
    metrics_directory: str | Path,
    output_directory: str | Path,
    formats: Iterable[str] = ("svg",),
    dpi: int = 150,
    incident_window: StageWindows = None,
    sim_duration_s: float = 3600.0,
    manifest: Mapping[str, Any] | None = None,
) -> list[Path]:
    metrics_path = Path(metrics_directory)
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    data = _read_aggregated(metrics_path)
    if not data:
        raise ValueError(f"No aggregated metrics found in {metrics_path}")

    paths: list[Path] = []
    efficiency_keys = (
        "total_travel_time_s",
        "mean_travel_time_s",
        "mean_delay_s",
        "total_delay_s",
        "throughput_veh_hour",
        "mean_speed_mps",
        "completed_vehicles",
    )
    for key in efficiency_keys:
        paths.extend(
            _plot_scalar_by_penetration(
                data,
                "efficiency",
                (key,),
                key.replace("_", " ").title(),
                key,
                output_path,
                formats,
                dpi,
            )
        )
        paths.extend(
            _plot_seed_boxplots(
                metrics_path,
                data,
                "efficiency",
                (key,),
                key.replace("_", " ").title(),
                output_path,
                formats,
                dpi,
            )
        )

    congestion_zones = sorted(
        {
            zone
            for _, values in data.items()
            for zone in values.get("congestion", {})
        }
    )
    for zone in congestion_zones:
        for key in (
            "mean_queue_length_m",
            "max_queue_length_m",
            "mean_congested_segments",
            "max_congested_segments",
        ):
            paths.extend(
                _plot_scalar_by_penetration(
                    data,
                    "congestion",
                    (zone, key),
                    f"{key.replace('_', ' ').title()} - {zone}",
                    key,
                    output_path,
                    formats,
                    dpi,
                )
            )

    stability_keys = (
        "mean_speed_std",
        "mean_accel_var",
        "hard_brake_events",
        "hard_brake_ratio",
        "mean_abs_jerk_mps3",
        "max_abs_jerk_mps3",
    )
    for key in stability_keys:
        for phase in ("pre_incident", "incident", "post_incident"):
            paths.extend(
                _plot_scalar_by_penetration(
                    data,
                    "stability",
                    (phase, key),
                    f"{key.replace('_', ' ').title()} - {phase}",
                    key,
                    output_path,
                    formats,
                    dpi,
                )
            )

    paths.extend(
        _plot_timeseries(
            metrics_path,
            "mean_speed_mps",
            "Mean speed over time",
            output_path,
            formats,
            dpi,
            incident_window,
            "metrics_stability_by_step",
        )
    )

    zone_names = sorted(
        {
            csv_file.name[len("metrics_congestion_"):-len("_by_interval.csv")]
            for penetration_directory in metrics_path.glob("p*")
            for strategy_directory in penetration_directory.iterdir()
            if strategy_directory.is_dir()
            for csv_file in strategy_directory.glob(
                "metrics_congestion_*_by_interval.csv"
            )
        }
    )
    for zone in zone_names:
        paths.extend(
            _plot_timeseries(
                metrics_path,
                "mean_queue_length_m",
                f"Mean queue length: {zone}",
                output_path,
                formats,
                dpi,
                incident_window,
                f"metrics_congestion_{zone}_by_interval",
            )
        )

    report_path = _write_report(output_path, paths, manifest)
    paths.append(report_path)
    return paths
