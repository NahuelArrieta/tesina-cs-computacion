"""Plot and export metrics for one or more experiment strategies."""

from __future__ import annotations

import base64
import csv
from dataclasses import dataclass
import html
import json
import math
import mimetypes
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["svg.hashsalt"] = "reproducible"

MetricData = dict[str, Any]
StageWindows = tuple[float, float] | None

BASELINE_STRATEGY = "m0"
ACTIVE_STRATEGIES = ("m1", "m2", "m3")
ALL_STRATEGIES = (BASELINE_STRATEGY, *ACTIVE_STRATEGIES)
STABILITY_PHASES = ("pre_incident", "incident", "post_incident")

CONGESTION_ZONE_ORDER = (
    "incident_street",
    "upstream_streets",
    "alternative_routes",
    "other_zones",
)

ZONE_LABELS = {
    "incident_street": "Incident",
    "upstream_streets": "Upstreams",
    "alternative_routes": "Alternatives",
    "other_zones": "Other zones",
}

METRIC_LABELS = {
    "total_travel_time_s": "Total travel time",
    "mean_travel_time_s": "Mean travel time",
    "mean_delay_s": "Mean delay",
    "total_delay_s": "Total delay",
    "throughput_veh_hour": "Throughput",
    "mean_speed_mps": "Mean speed",
    "completed_vehicles": "Completed vehicles",
    "mean_queue_length_m": "Mean queue length",
    "max_queue_length_m": "Maximum queue length",
    "mean_congested_segments": "Mean congested segments",
    "max_congested_segments": "Maximum congested segments",
    "mean_speed_std": "Speed standard deviation",
    "mean_accel_var": "Acceleration variance",
    "hard_brake_events": "Hard-braking events",
    "hard_brake_ratio": "Hard-braking ratio",
    "mean_abs_jerk_mps3": "Mean absolute jerk",
    "max_abs_jerk_mps3": "Maximum absolute jerk",
}

EFFICIENCY_KEYS = (
    "mean_travel_time_s",
    "mean_delay_s",
    "throughput_veh_hour",
    "mean_speed_mps",
)

CONGESTION_METRICS = (
    ("mean_queue_length_m", "Mean queue length (m)"),
    ("max_queue_length_m", "Maximum queue length (m)"),
    ("mean_congested_segments", "Mean congested segments"),
    ("max_congested_segments", "Maximum congested segments"),
)

CONGESTION_TIMESERIES_METRICS = (
    ("mean_queue_length_m", "Mean queue length over time", "Mean queue length (m)"),
    ("max_queue_length_m", "Maximum queue length over time", "Maximum queue length (m)"),
)

STABILITY_KEYS = (
    "mean_speed_std",
    "mean_accel_var",
    "hard_brake_events",
    "hard_brake_ratio",
    "mean_abs_jerk_mps3",
    "max_abs_jerk_mps3",
)

STRATEGY_STYLES: dict[str, dict[str, Any]] = {
    "m0": {"color": "#666666", "linestyle": ":", "linewidth": 1.6},
    "m1": {"linestyle": "-", "marker": "o", "markersize": 7, "alpha": 0.9},
    "m2": {"linestyle": "--", "marker": "s", "markersize": 6, "alpha": 0.9},
    "m3": {"linestyle": "-.", "marker": "^", "markersize": 5, "alpha": 0.9},
}


@dataclass(frozen=True)
class PlotConfig:
    output_directory: Path
    formats: tuple[str, ...]
    dpi: int


@dataclass(frozen=True)
class PlotArtifact:
    path: Path
    title: str
    is_grid: bool



def _human_metric_label(metric_name: str) -> str:
    return METRIC_LABELS.get(metric_name, metric_name.replace("_", " ").title())


def _human_zone_label(zone: str) -> str:
    return ZONE_LABELS.get(zone, zone.replace("_", " ").title())


def _get_nested(mapping: Any, keys: Sequence[str]) -> Any:
    current = mapping
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _aggregate_value(value: Any) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return float(value.get("mean", 0.0)), float(value.get("std", 0.0))
    return float(value), 0.0


def _discover_penetrations(metrics_directory: Path, *, positive_only: bool = True) -> list[int]:
    penetrations: list[int] = []
    for path in metrics_directory.glob("p*"):
        if not path.is_dir() or not path.name[1:].isdigit():
            continue
        value = int(path.name[1:])
        if not positive_only or value > 0:
            penetrations.append(value)
    return sorted(penetrations)


def _positive_penetrations(data: Mapping[tuple[int, str], MetricData]) -> list[int]:
    return sorted({penetration for penetration, _ in data if penetration > 0})


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Time-series file not found: {path}")
    with path.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def _read_aggregated(metrics_directory: Path) -> dict[tuple[int, str], MetricData]:
    data: dict[tuple[int, str], MetricData] = {}
    for penetration in _discover_penetrations(metrics_directory, positive_only=False):
        penetration_dir = metrics_directory / f"p{penetration}"
        for strategy_dir in penetration_dir.iterdir():
            if not strategy_dir.is_dir():
                continue
            metrics_file = strategy_dir / "metrics.json"
            if metrics_file.is_file():
                data[(penetration, strategy_dir.name)] = json.loads(
                    metrics_file.read_text(encoding="utf-8")
                )
    return data


def _moving_average(
    values: list[float],
    xs: list[float],
    window_s: float,
) -> list[float]:
    """Return a centered moving average using a time-based window."""
    if len(values) < 2 or window_s <= 0:
        return values
    step_s = (xs[-1] - xs[0]) / (len(xs) - 1)
    if step_s <= 0:
        return values
    window_samples = max(1, round(window_s / step_s))
    if window_samples % 2 == 0:
        window_samples += 1
    if window_samples == 1:
        return values

    half_window = window_samples // 2
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)

    n = len(values)
    return [
        (prefix[min(n, i + half_window + 1)] - prefix[max(0, i - half_window)])
        / (min(n, i + half_window + 1) - max(0, i - half_window))
        for i in range(n)
    ]


def _create_grid(
    n_items: int,
    *,
    ncols: int = 2,
    figsize_per_cell: tuple[float, float] = (6.0, 4.0),
) -> tuple[plt.Figure, list[plt.Axes]]:
    nrows = max(1, math.ceil(n_items / ncols))
    figsize = (figsize_per_cell[0] * ncols, figsize_per_cell[1] * nrows)
    figure, axes = plt.subplots(
        nrows,
        ncols,
        figsize=figsize,
        constrained_layout=True,
        squeeze=False,
    )
    flat_axes = list(axes.flat)
    for axis in flat_axes[n_items:]:
        axis.set_visible(False)
    return figure, flat_axes[:n_items]


def _draw_stage_boundaries(axis: plt.Axes, incident_window: StageWindows) -> None:
    if incident_window is None:
        return
    incident_start_s, incident_end_s = incident_window
    x_min, x_max = axis.get_xlim()
    stages = (
        (x_min, incident_start_s, "#4c78a8", 0.10, "Pre-incident"),
        (incident_start_s, incident_end_s, "#e45756", 0.12, "Incident"),
        (incident_end_s, x_max, "#59a14f", 0.10, "Post-incident"),
    )
    for start, end, color, alpha, label in stages:
        axis.axvspan(start, end, color=color, alpha=alpha, label=label, zorder=0)
    axis.axvline(incident_start_s, color="#b22222", linestyle="--", linewidth=1.2)
    axis.axvline(incident_end_s, color="#b22222", linestyle="--", linewidth=1.2)


def _plot_penetration_curves(
    axis: plt.Axes,
    data: Mapping[tuple[int, str], MetricData],
    penetrations: Sequence[int],
    key_path: Sequence[str],
    *,
    capsize: int = 3,
) -> bool:
    """Plot active strategies with error bars and M0 baseline. Returns True if any data was plotted."""
    has_data = False
    for strategy in ACTIVE_STRATEGIES:
        xs, ys, errors = [], [], []
        for penetration in penetrations:
            raw = _get_nested(data.get((penetration, strategy)), key_path)
            if raw is None:
                continue
            try:
                mean, std = _aggregate_value(raw)
            except (TypeError, ValueError):
                continue
            xs.append(penetration)
            ys.append(mean)
            errors.append(std)
        if xs:
            style = STRATEGY_STYLES.get(strategy, {})
            axis.errorbar(
                xs,
                ys,
                yerr=errors,
                capsize=capsize,
                label=strategy.upper(),
                **style,
            )
            has_data = True

    baseline_raw = _get_nested(data.get((0, BASELINE_STRATEGY)), key_path)
    if baseline_raw is not None:
        try:
            mean, _ = _aggregate_value(baseline_raw)
            axis.axhline(mean, color="#444", linestyle=":", label="M0")
            has_data = True
        except (TypeError, ValueError):
            pass

    return has_data


def _add_shared_legend(figure: plt.Figure, axis: plt.Axes) -> None:
    handles, labels = axis.get_legend_handles_labels()
    if handles:
        figure.legend(handles, labels, loc="upper center", ncol=4)


def _save_figure(
    figure: plt.Figure,
    config: PlotConfig,
    stem: str,
    title: str,
    *,
    is_grid: bool,
) -> list[PlotArtifact]:
    artifacts: list[PlotArtifact] = []
    try:
        for file_format in config.formats:
            if file_format != "svg":
                raise ValueError(f"Unsupported output format: {file_format}")
            path = config.output_directory / f"{stem}.{file_format}"
            figure.savefig(path, dpi=config.dpi, bbox_inches="tight", metadata={"Date": None})
            artifacts.append(PlotArtifact(path=path, title=title, is_grid=is_grid))
    finally:
        plt.close(figure)
    return artifacts


def _plot_scalar_by_penetration(
    data: Mapping[tuple[int, str], MetricData],
    section: str,
    leaf_path: tuple[str, ...],
    title: str,
    ylabel: str,
    config: PlotConfig,
) -> list[PlotArtifact]:
    penetrations = _positive_penetrations(data)
    if not penetrations:
        return []

    figure, axis = plt.subplots(figsize=(10, 6), constrained_layout=True)
    has_data = _plot_penetration_curves(
        axis, data, penetrations, (section, *leaf_path), capsize=4
    )
    if not has_data:
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
        config,
        f"{section}_{'_'.join(leaf_path)}",
        title,
        is_grid=False,
    )


def _plot_seed_boxplots(
    data: Mapping[tuple[int, str], MetricData],
    section: str,
    leaf_path: tuple[str, ...],
    title: str,
    config: PlotConfig,
) -> list[PlotArtifact]:
    penetrations = _positive_penetrations(data)
    if not penetrations:
        return []

    figure, axes = _create_grid(len(penetrations), ncols=2, figsize_per_cell=(6.0, 4.0))
    key_path = (section, *leaf_path)

    for axis, penetration in zip(axes, penetrations):
        box_data: list[list[float]] = []
        labels: list[str] = []
        for strategy in ALL_STRATEGIES:
            source_penetration = 0 if strategy == BASELINE_STRATEGY else penetration
            raw = _get_nested(data.get((source_penetration, strategy)), key_path)
            samples = raw.get("values") if isinstance(raw, Mapping) else None
            if isinstance(samples, list) and samples:
                try:
                    box_data.append([float(v) for v in samples])
                    labels.append(strategy.upper())
                except (TypeError, ValueError):
                    continue
        if box_data:
            axis.boxplot(box_data, tick_labels=labels)
        axis.set_xlabel(f"{penetration}% CAV")
        axis.grid(axis="y", alpha=0.25)

    figure.suptitle(f"{title} across penetration levels")
    return _save_figure(
        figure,
        config,
        f"boxplot_{section}_{'_'.join(leaf_path)}",
        f"{title} distribution across penetration levels",
        is_grid=True,
    )


def _plot_stability_by_phase(
    data: Mapping[tuple[int, str], MetricData],
    metric_name: str,
    config: PlotConfig,
) -> list[PlotArtifact]:
    penetrations = _positive_penetrations(data)
    if not penetrations:
        return []

    figure, axes = _create_grid(
        len(STABILITY_PHASES), ncols=3, figsize_per_cell=(5.0, 5.0)
    )
    metric_label = _human_metric_label(metric_name)

    for axis, phase in zip(axes, STABILITY_PHASES):
        _plot_penetration_curves(
            axis, data, penetrations, ("stability", phase, metric_name)
        )
        axis.set_title(phase.replace("_", " ").title())
        axis.set_xlabel("CAV penetration (%)")
        axis.set_xticks(penetrations)
        axis.grid(axis="y", alpha=0.25)

    axes[0].set_ylabel(metric_label)
    _add_shared_legend(figure, axes[0])
    title = f"{metric_label} by incident phase"
    figure.suptitle(title)
    return _save_figure(
        figure,
        config,
        f"stability_{metric_name}_by_phase",
        title,
        is_grid=True,
    )


def _plot_congestion_metric_grid(
    data: Mapping[tuple[int, str], MetricData],
    metric_name: str,
    ylabel: str,
    config: PlotConfig,
) -> list[PlotArtifact]:
    penetrations = _positive_penetrations(data)
    if not penetrations:
        return []

    figure, axes = _create_grid(
        len(CONGESTION_ZONE_ORDER), ncols=2, figsize_per_cell=(6.0, 4.0)
    )
    for axis, zone in zip(axes, CONGESTION_ZONE_ORDER):
        _plot_penetration_curves(
            axis, data, penetrations, ("congestion", zone, metric_name)
        )
        axis.set_title(_human_zone_label(zone))
        axis.set_xlabel("CAV penetration (%)")
        axis.set_ylabel(ylabel)
        axis.set_xticks(penetrations)
        axis.grid(axis="y", alpha=0.25)

    _add_shared_legend(figure, axes[0])
    title = f"{_human_metric_label(metric_name)} by congestion zone"
    figure.suptitle(title)
    return _save_figure(
        figure,
        config,
        f"congestion_{metric_name}_by_zone",
        title,
        is_grid=True,
    )


def _plot_speed_timeseries_grid(
    metrics_directory: Path,
    config: PlotConfig,
    incident_window: StageWindows,
) -> list[PlotArtifact]:
    penetrations = _discover_penetrations(metrics_directory, positive_only=True)
    if not penetrations:
        return []

    figure, axes = _create_grid(
        len(penetrations), ncols=2, figsize_per_cell=(6.5, 4.0)
    )
    for axis, penetration in zip(axes, penetrations):
        for strategy in ALL_STRATEGIES:
            source_penetration = 0 if strategy == BASELINE_STRATEGY else penetration
            csv_file = (
                metrics_directory
                / f"p{source_penetration}"
                / strategy
                / "metrics_stability_by_step.csv"
            )
            if not csv_file.is_file():
                continue
            rows = _read_csv(csv_file)
            if not rows:
                continue

            xs = [float(row["time"]) for row in rows]
            ys = _moving_average(
                [float(row["mean_speed_mps"]) for row in rows], xs, 60.0
            )
            stds = _moving_average(
                [float(row.get("mean_speed_mps_std", 0.0)) for row in rows],
                xs,
                60.0,
            )

            style = STRATEGY_STYLES.get(strategy, {})
            if strategy == BASELINE_STRATEGY:
                axis.plot(xs, ys, label="M0 (baseline)", **style)
            else:
                axis.plot(
                    xs,
                    ys,
                    label=strategy.upper(),
                    linestyle=style.get("linestyle", "-"),
                    alpha=style.get("alpha", 0.9),
                )

        _draw_stage_boundaries(axis, incident_window)
        axis.set_title(f"{penetration}% CAV")
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Mean speed (m/s)")
        axis.grid(alpha=0.25)

    _add_shared_legend(figure, axes[0])
    title = "Mean speed over time - 60 s moving average"
    figure.suptitle(title)
    return _save_figure(
        figure,
        config,
        "metrics_mean_speed_by_penetration",
        title,
        is_grid=True,
    )


def _plot_congestion_timeseries_grid(
    metrics_directory: Path,
    zones: Sequence[str],
    metric_name: str,
    title: str,
    ylabel: str,
    config: PlotConfig,
    incident_window: StageWindows,
) -> list[PlotArtifact]:
    if not zones:
        return []

    artifacts: list[PlotArtifact] = []
    penetrations = _discover_penetrations(metrics_directory, positive_only=True)

    for penetration in penetrations:
        figure, axes = _create_grid(len(zones), ncols=2, figsize_per_cell=(6.5, 4.0))
        for axis, zone in zip(axes, zones):
            for strategy in ALL_STRATEGIES:
                source_penetration = (
                    0 if strategy == BASELINE_STRATEGY else penetration
                )
                csv_file = (
                    metrics_directory
                    / f"p{source_penetration}"
                    / strategy
                    / f"metrics_congestion_{zone}_by_interval.csv"
                )
                if not csv_file.is_file():
                    continue
                rows = _read_csv(csv_file)
                if not rows:
                    continue

                xs = [float(row["interval_midpoint_s"]) for row in rows]
                values = [float(row[metric_name]) for row in rows]
                style = STRATEGY_STYLES.get(strategy, {})
                if strategy == BASELINE_STRATEGY:
                    axis.plot(xs, values, label="M0", **style)
                else:
                    axis.plot(
                        xs,
                        values,
                        label=strategy.upper(),
                        linestyle=style.get("linestyle", "-"),
                        marker=style.get("marker"),
                        markersize=style.get("markersize"),
                        markevery=max(1, len(xs) // 10),  # ~10 marcadores por curva
                        alpha=style.get("alpha", 0.9),
                    )
            _draw_stage_boundaries(axis, incident_window)
            axis.set_title(_human_zone_label(zone))
            axis.set_xlabel("Time (s)")
            axis.set_ylabel(ylabel)
            axis.grid(alpha=0.25)

        _add_shared_legend(figure, axes[0])
        figure.suptitle(f"{title} by congestion zone - {penetration}% CAV")
        report_title = f"{_human_metric_label(metric_name)} over time - {penetration}% CAV"
        artifacts.extend(
            _save_figure(
                figure,
                config,
                f"metrics_congestion_{metric_name}_by_zone_p{penetration}",
                report_title,
                is_grid=True,
            )
        )
    return artifacts



def _write_report(
    output_directory: Path,
    artifacts: Sequence[PlotArtifact],
    manifest: Mapping[str, Any] | None = None,
) -> Path:
    sections: list[str] = []
    for artifact in artifacts:
        if artifact.path.suffix.lower() != ".svg":
            continue
        title = html.escape(artifact.title)
        image_class = "plot-grid" if artifact.is_grid else "plot-single"
        content = base64.b64encode(artifact.path.read_bytes()).decode("ascii")
        mime_type = (
            mimetypes.guess_type(artifact.path.name)[0] or "application/octet-stream"
        )
        sections.append(
            f"<h2>{title}</h2>"
            f'<img class="{image_class}" src="data:{mime_type};base64,{content}" '
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
        '<!doctype html><html><head><meta charset="utf-8">'
        "<title>Metrics visualizations</title>"
        "<style>body{font-family:sans-serif;max-width:1200px;margin:auto}"
        "img{display:block;margin-bottom:2rem}"
        ".plot-grid{max-width:100%}"
        ".plot-single{max-width:50%;}"
        "pre{background:#f5f5f5;padding:1rem;overflow:auto}</style>"
        "</head><body><h1>Metrics visualizations</h1>"
        + manifest_section
        + "".join(sections)
        + "</body></html>\n",
        encoding="utf-8",
    )
    return report_path


def _discover_congestion_zones(metrics_directory: Path) -> list[str]:
    prefix = "metrics_congestion_"
    suffix = "_by_interval.csv"
    discovered = {
        csv_file.name[len(prefix) : -len(suffix)]
        for penetration in _discover_penetrations(metrics_directory, positive_only=True)
        for strategy_dir in (metrics_directory / f"p{penetration}").iterdir()
        if strategy_dir.is_dir()
        for csv_file in strategy_dir.glob(f"{prefix}*{suffix}")
    }
    return [zone for zone in CONGESTION_ZONE_ORDER if zone in discovered]


def _cleanup_stale_svgs(output_directory: Path, artifacts: Sequence[PlotArtifact]) -> None:
    retained = {
        artifact.path.resolve()
        for artifact in artifacts
        if artifact.path.suffix.lower() == ".svg"
    }
    for stale_svg in output_directory.glob("*.svg"):
        if stale_svg.resolve() not in retained:
            stale_svg.unlink()


def visualize_metrics(
    metrics_directory: str | Path,
    output_directory: str | Path,
    formats: Iterable[str] = ("svg",),
    dpi: int = 150,
    incident_window: StageWindows = None,
    manifest: Mapping[str, Any] | None = None,
) -> list[Path]:
    metrics_path = Path(metrics_directory)
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    data = _read_aggregated(metrics_path)
    if not data:
        raise ValueError(f"No aggregated metrics found in {metrics_path}")

    config = PlotConfig(
        output_directory=output_path,
        formats=tuple(formats),
        dpi=dpi,
    )
    artifacts: list[PlotArtifact] = []

    for key in EFFICIENCY_KEYS:
        label = _human_metric_label(key)
        artifacts.extend(
            _plot_scalar_by_penetration(data, "efficiency", (key,), label, label, config)
        )
        artifacts.extend(
            _plot_seed_boxplots(data, "efficiency", (key,), label, config)
        )

    has_congestion = any(
        zone in values.get("congestion", {})
        for values in data.values()
        for zone in CONGESTION_ZONE_ORDER
    )
    if has_congestion:
        for metric_name, ylabel in CONGESTION_METRICS:
            artifacts.extend(
                _plot_congestion_metric_grid(data, metric_name, ylabel, config)
            )

    for key in STABILITY_KEYS:
        artifacts.extend(_plot_stability_by_phase(data, key, config))

    artifacts.extend(
        _plot_speed_timeseries_grid(metrics_path, config, incident_window)
    )

    zone_names = _discover_congestion_zones(metrics_path)
    for metric_name, title, ylabel in CONGESTION_TIMESERIES_METRICS:
        artifacts.extend(
            _plot_congestion_timeseries_grid(
                metrics_path,
                zone_names,
                metric_name,
                title,
                ylabel,
                config,
                incident_window,
            )
        )

    _cleanup_stale_svgs(output_path, artifacts)
    report_path = _write_report(output_path, artifacts, manifest)
    return [artifact.path for artifact in artifacts] + [report_path]