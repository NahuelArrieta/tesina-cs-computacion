"""Plot and export metrics for one or more experiment strategies."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import html
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["svg.hashsalt"] = "reproducible"

MetricData = dict[str, Any]
StageWindows = tuple[float, float] | None

## Constants and configuration
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


@dataclass(frozen=True)
class MetricSpec:
    label: str
    unit: str | None = None

    @property
    def ylabel(self) -> str:
        return f"{self.label} ({self.unit})" if self.unit else self.label


METRICS: dict[str, MetricSpec] = {
    "total_travel_time_s": MetricSpec("Total travel time", "s"),
    "mean_travel_time_s": MetricSpec("Mean travel time", "s"),
    "mean_delay_s": MetricSpec("Mean delay", "s"),
    "total_delay_s": MetricSpec("Total delay", "s"),
    "throughput_veh_hour": MetricSpec("Throughput", "veh/h"),
    "mean_speed_mps": MetricSpec("Mean speed", "m/s"),
    "completed_vehicles": MetricSpec("Completed vehicles"),
    "mean_queue_length_m": MetricSpec("Mean queue length", "m"),
    "max_queue_length_m": MetricSpec("Maximum queue length", "m"),
    "mean_congested_segments": MetricSpec("Mean congested segments"),
    "max_congested_segments": MetricSpec("Maximum congested segments"),
    "mean_speed_std": MetricSpec("Speed standard deviation", "m/s"),
    "mean_accel_var": MetricSpec("Acceleration variance", "m²/s⁴"),
    "hard_brake_events": MetricSpec("Hard-braking events"),
    "hard_brake_ratio": MetricSpec("Hard-braking ratio"),
    "mean_abs_jerk_mps3": MetricSpec("Mean absolute jerk", "m/s³"),
    "max_abs_jerk_mps3": MetricSpec("Maximum absolute jerk", "m/s³"),
}

EFFICIENCY_KEYS = (
    "mean_travel_time_s",
    "mean_delay_s",
    "throughput_veh_hour",
    "mean_speed_mps",
)

CONGESTION_KEYS = (
    "mean_queue_length_m",
    "max_queue_length_m",
    "mean_congested_segments",
    "max_congested_segments",
)

CONGESTION_TIMESERIES_KEYS = (
    "mean_queue_length_m",
    "max_queue_length_m",
)

STABILITY_KEYS = (
    "mean_speed_std",
    "mean_accel_var",
    "hard_brake_events",
    "hard_brake_ratio",
    "mean_abs_jerk_mps3",
    "max_abs_jerk_mps3",
)


@dataclass(frozen=True)
class PlotTheme:
    strategy_styles: Mapping[str, Mapping[str, Any]]
    grid_alpha: float = 0.25
    legend_loc: str = "outside lower center"
    legend_max_cols: int = 4
    layout_pad: Mapping[str, float] = None  # type: ignore[assignment]
    save_pad_inches: float = 0.25

    def __post_init__(self) -> None:
        if self.layout_pad is None:
            object.__setattr__(
                self,
                "layout_pad",
                {"w_pad": 0.15, "h_pad": 0.15, "hspace": 0.12, "wspace": 0.08},
            )


THEME = PlotTheme(
    strategy_styles={
        "m0": {"color": "#666666", "linestyle": ":", "linewidth": 1.6},
        "m1": {"linestyle": "-", "marker": "o", "markersize": 7, "alpha": 0.9},
        "m2": {"linestyle": "--", "marker": "s", "markersize": 6, "alpha": 0.9},
        "m3": {"linestyle": "-.", "marker": "^", "markersize": 5, "alpha": 0.9},
    }
)


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


def _metric_spec(metric_name: str) -> MetricSpec:
    return METRICS.get(metric_name, MetricSpec(metric_name.replace("_", " ").title()))


def _zone_label(zone: str) -> str:
    return ZONE_LABELS.get(zone, zone.replace("_", " ").title())

## Utility functions

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


def _moving_average(values: list[float], xs: list[float], window_s: float) -> list[float]:
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

    half = window_samples // 2
    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + v)
    n = len(values)
    return [
        (prefix[min(n, i + half + 1)] - prefix[max(0, i - half)])
        / (min(n, i + half + 1) - max(0, i - half))
        for i in range(n)
    ]


class ExperimentStore:
    """Encapsulates all reads from metrics_directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.aggregated = self._load_aggregated()
        self.penetrations = sorted({p for p, _ in self.aggregated if p > 0})

    def _discover_penetration_dirs(self, *, positive_only: bool) -> list[int]:
        found = []
        for path in self.root.glob("p*"):
            if path.is_dir() and path.name[1:].isdigit():
                val = int(path.name[1:])
                if not positive_only or val > 0:
                    found.append(val)
        return sorted(found)

    def _load_aggregated(self) -> dict[tuple[int, str], MetricData]:
        data: dict[tuple[int, str], MetricData] = {}
        for p in self._discover_penetration_dirs(positive_only=False):
            for strategy_dir in (self.root / f"p{p}").iterdir():
                metrics_file = strategy_dir / "metrics.json"
                if strategy_dir.is_dir() and metrics_file.is_file():
                    data[(p, strategy_dir.name)] = json.loads(
                        metrics_file.read_text(encoding="utf-8")
                    )
        return data

    def get_aggregate(
        self, penetration: int, strategy: str, key_path: Sequence[str]
    ) -> tuple[float, float] | None:
        raw = _get_nested(self.aggregated.get((penetration, strategy)), key_path)
        if raw is None:
            return None
        try:
            return _aggregate_value(raw)
        except (TypeError, ValueError):
            return None

    def get_samples(
        self, penetration: int, strategy: str, key_path: Sequence[str]
    ) -> list[float]:
        raw = _get_nested(self.aggregated.get((penetration, strategy)), key_path)
        samples = raw.get("values") if isinstance(raw, Mapping) else None
        if not isinstance(samples, list) or not samples:
            return []
        try:
            return [float(v) for v in samples]
        except (TypeError, ValueError):
            return []

    def has_congestion_data(self) -> bool:
        return any(
            zone in values.get("congestion", {})
            for values in self.aggregated.values()
            for zone in CONGESTION_ZONE_ORDER
        )

    def discover_congestion_zones(self) -> list[str]:
        prefix, suffix = "metrics_congestion_", "_by_interval.csv"
        discovered = {
            csv_file.name[len(prefix) : -len(suffix)]
            for p in self._discover_penetration_dirs(positive_only=True)
            for strategy_dir in (self.root / f"p{p}").iterdir()
            if strategy_dir.is_dir()
            for csv_file in strategy_dir.glob(f"{prefix}*{suffix}")
        }
        return [z for z in CONGESTION_ZONE_ORDER if z in discovered]

    def read_csv(self, penetration: int, strategy: str, filename: str) -> list[dict[str, str]]:
        source_p = 0 if strategy == BASELINE_STRATEGY else penetration
        path = self.root / f"p{source_p}" / strategy / filename
        if not path.is_file():
            return []
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))


## Layout and styling helpers
def _create_grid(
    n_items: int,
    *,
    ncols: int = 2,
    figsize_per_cell: tuple[float, float] = (6.0, 4.0),
    sharey: bool = False,
) -> tuple[plt.Figure, list[plt.Axes]]:
    nrows = max(1, math.ceil(n_items / ncols))
    figure, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(figsize_per_cell[0] * ncols, figsize_per_cell[1] * nrows),
        layout="constrained",
        squeeze=False,
        sharey=sharey,
    )
    engine = figure.get_layout_engine()
    if engine is not None:
        engine.set(**THEME.layout_pad)

    flat_axes = list(axes.flat)
    for axis in flat_axes[n_items:]:
        axis.set_visible(False)
    return figure, flat_axes[:n_items]


def _style_axis(
    axis: plt.Axes,
    *,
    title: str,
    xlabel: str,
    ylabel: str | None = None,
    xticks: Sequence[int] | None = None,
    grid_axis: str = "y",
) -> None:
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    if ylabel:
        axis.set_ylabel(ylabel)
    if xticks is not None:
        axis.set_xticks(xticks)
    axis.grid(axis=grid_axis, alpha=THEME.grid_alpha)


def _draw_stage_boundaries(axis: plt.Axes, incident_window: StageWindows) -> None:
    if incident_window is None:
        return
    start_s, end_s = incident_window
    x_min, x_max = axis.get_xlim()
    stages = (
        (x_min, start_s, "#4c78a8", 0.10, "Pre-incident"),
        (start_s, end_s, "#e45756", 0.12, "Incident"),
        (end_s, x_max, "#59a14f", 0.10, "Post-incident"),
    )
    for s, e, color, alpha, label in stages:
        axis.axvspan(s, e, color=color, alpha=alpha, label=label, zorder=0)
    axis.axvline(start_s, color="#b22222", linestyle="--", linewidth=1.2)
    axis.axvline(end_s, color="#b22222", linestyle="--", linewidth=1.2)


def _add_shared_legend(figure: plt.Figure, axis: plt.Axes) -> None:
    handles, labels = axis.get_legend_handles_labels()
    if handles:
        figure.legend(
            handles,
            labels,
            loc=THEME.legend_loc,
            ncol=min(len(handles), THEME.legend_max_cols),
        )


def _save_figure(
    figure: plt.Figure,
    config: PlotConfig,
    stem: str,
    title: str,
    *,
    is_grid: bool,
) -> list[PlotArtifact]:
    artifacts: list[PlotArtifact] = []
    extra_artists = [*figure.legends, *figure.texts]
    try:
        for fmt in config.formats:
            if fmt != "svg":
                raise ValueError(f"Unsupported output format: {fmt}")
            path = config.output_directory / f"{stem}.{fmt}"
            figure.savefig(
                path,
                dpi=config.dpi,
                bbox_inches="tight",
                bbox_extra_artists=extra_artists,
                pad_inches=THEME.save_pad_inches,
                metadata={"Date": None},
            )
            artifacts.append(PlotArtifact(path=path, title=title, is_grid=is_grid))
    finally:
        plt.close(figure)
    return artifacts


## Generic plot constructors

def _draw_penetration_curves(
    axis: plt.Axes,
    store: ExperimentStore,
    key_path: Sequence[str],
    *,
    capsize: int = 3,
) -> bool:
    has_data = False
    for strategy in ACTIVE_STRATEGIES:
        xs, ys, errs = [], [], []
        for p in store.penetrations:
            agg = store.get_aggregate(p, strategy, key_path)
            if agg is not None:
                xs.append(p)
                ys.append(agg[0])
                errs.append(agg[1])
        if xs:
            axis.errorbar(
                xs,
                ys,
                yerr=errs,
                capsize=capsize,
                label=strategy.upper(),
                **THEME.strategy_styles.get(strategy, {}),
            )
            has_data = True

    baseline = store.get_aggregate(0, BASELINE_STRATEGY, key_path)
    if baseline is not None:
        axis.axhline(
            baseline[0],
            label="M0",
            **THEME.strategy_styles[BASELINE_STRATEGY],
        )
        has_data = True
    return has_data


def _plot_penetration_grid(
    store: ExperimentStore,
    panels: Sequence[tuple[str, Sequence[str]]],
    *,
    title: str,
    ylabel: str,
    stem: str,
    config: PlotConfig,
    ncols: int = 2,
    figsize_per_cell: tuple[float, float] = (6.0, 4.0),
    sharey: bool = False,
) -> list[PlotArtifact]:
    """Generic builder for 1-panel or multi-panel penetration curve plots."""
    if not store.penetrations or not panels:
        return []

    is_grid = len(panels) > 1
    figure, axes = _create_grid(
        len(panels),
        ncols=ncols if is_grid else 1,
        figsize_per_cell=figsize_per_cell if is_grid else (10.0, 6.0),
        sharey=sharey,
    )

    any_data = False
    for idx, (axis, (panel_title, key_path)) in enumerate(zip(axes, panels)):
        if _draw_penetration_curves(axis, store, key_path, capsize=3 if is_grid else 4):
            any_data = True
        show_ylabel = (not sharey) or (idx % ncols == 0)
        _style_axis(
            axis,
            title=panel_title,
            xlabel="CAV penetration (%)",
            ylabel=ylabel if show_ylabel else None,
            xticks=store.penetrations,
        )

    if not any_data:
        plt.close(figure)
        return []

    if is_grid:
        _add_shared_legend(figure, axes[0])
        figure.suptitle(title)
    else:
        axes[0].legend()

    return _save_figure(figure, config, stem, title, is_grid=is_grid)


def _plot_boxplots_by_penetration(
    store: ExperimentStore,
    section: str,
    metric_name: str,
    config: PlotConfig,
) -> list[PlotArtifact]:
    if not store.penetrations:
        return []

    spec = _metric_spec(metric_name)
    ncols = 2
    figure, axes = _create_grid(
        len(store.penetrations),
        ncols=ncols,
        figsize_per_cell=(6.0, 4.0),
        sharey=True,
    )
    key_path = (section, metric_name)

    for idx, (axis, p) in enumerate(zip(axes, store.penetrations)):
        box_data, labels = [], []
        for strategy in ALL_STRATEGIES:
            source_p = 0 if strategy == BASELINE_STRATEGY else p
            samples = store.get_samples(source_p, strategy, key_path)
            if samples:
                box_data.append(samples)
                labels.append(strategy.upper())
        if box_data:
            axis.boxplot(box_data, tick_labels=labels)
        _style_axis(
            axis,
            title=f"{p}% CAV",
            xlabel="Strategy",
            ylabel=spec.ylabel if idx % ncols == 0 else None,
        )

    figure.suptitle(f"{spec.label} across penetration levels")
    return _save_figure(
        figure,
        config,
        f"boxplot_{section}_{metric_name}",
        f"{spec.label} distribution across penetration levels",
        is_grid=True,
    )


def _plot_timeseries_by_penetration(
    store: ExperimentStore,
    *,
    filename: str,
    x_col: str,
    y_col: str,
    title: str,
    ylabel: str,
    stem: str,
    config: PlotConfig,
    incident_window: StageWindows,
    smooth_window_s: float = 0.0,
    with_markers: bool = False,
    sharey: bool = True,
) -> list[PlotArtifact]:
    """Generic builder for 2x2 time-series grids grouped by penetration."""
    if not store.penetrations:
        return []

    ncols = 2
    figure, axes = _create_grid(
        len(store.penetrations),
        ncols=ncols,
        figsize_per_cell=(6.5, 4.0),
        sharey=sharey,
    )

    for idx, (axis, p) in enumerate(zip(axes, store.penetrations)):
        for strategy in ALL_STRATEGIES:
            rows = store.read_csv(p, strategy, filename)
            if not rows:
                continue
            xs = [float(r[x_col]) for r in rows]
            ys = [float(r[y_col]) for r in rows]
            if smooth_window_s > 0:
                ys = _moving_average(ys, xs, smooth_window_s)

            style = THEME.strategy_styles.get(strategy, {})
            if strategy == BASELINE_STRATEGY:
                axis.plot(xs, ys, label="M0", **style)
            else:
                plot_kwargs: dict[str, Any] = {
                    "label": strategy.upper(),
                    "linestyle": style.get("linestyle", "-"),
                    "alpha": style.get("alpha", 0.9),
                }
                if with_markers:
                    plot_kwargs.update(
                        marker=style.get("marker"),
                        markersize=style.get("markersize"),
                        markevery=max(1, len(xs) // 10),
                    )
                axis.plot(xs, ys, **plot_kwargs)

        _draw_stage_boundaries(axis, incident_window)
        _style_axis(
            axis,
            title=f"{p}% CAV",
            xlabel="Time (s)",
            ylabel=ylabel if (not sharey or idx % ncols == 0) else None,
            grid_axis="both",
        )

    _add_shared_legend(figure, axes[0])
    figure.suptitle(title)
    return _save_figure(figure, config, stem, title, is_grid=True)

## Report generation

def _write_report(
    output_directory: Path,
    artifacts: Sequence[PlotArtifact],
    manifest: Mapping[str, Any] | None = None,
) -> Path:
    report_path = output_directory.parent / "report.html"
    sections: list[str] = []
    for artifact in artifacts:
        if artifact.path.suffix.lower() != ".svg":
            continue
        title = html.escape(artifact.title)
        image_class = "plot-grid" if artifact.is_grid else "plot-single"
        relative_path = artifact.path.relative_to(report_path.parent).as_posix()
        src = html.escape(quote(relative_path, safe="/"), quote=True)
        sections.append(
            f"<h2>{title}</h2>"
            f'<img class="{image_class}" src="{src}" '
            f'alt="{title}" />'
        )

    manifest_section = ""
    if manifest is not None:
        description = html.escape(str(manifest.get("description", "")))
        manifest_json = html.escape(json.dumps(manifest, indent=2, ensure_ascii=False))
        manifest_section = (
            "<section><h2>Experiment data</h2>"
            f"<p><strong>Description:</strong> {description}</p>"
            "<details><summary>Manifest JSON</summary>"
            f"<pre>{manifest_json}</pre>"
            "</details></section>"
        )

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


def _cleanup_stale_svgs(output_directory: Path, artifacts: Sequence[PlotArtifact]) -> None:
    retained = {
        a.path.resolve() for a in artifacts if a.path.suffix.lower() == ".svg"
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
    store = ExperimentStore(Path(metrics_directory))
    if not store.aggregated:
        raise ValueError(f"No aggregated metrics found in {store.root}")

    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    config = PlotConfig(output_directory=output_path, formats=tuple(formats), dpi=dpi)

    artifacts: list[PlotArtifact] = []

    # 1. Efficiency
    for key in EFFICIENCY_KEYS:
        spec = _metric_spec(key)
        artifacts.extend(
            _plot_penetration_grid(
                store,
                [(spec.label, ("efficiency", key))],
                title=spec.label,
                ylabel=spec.ylabel,
                stem=f"efficiency_{key}",
                config=config,
            )
        )
        artifacts.extend(_plot_boxplots_by_penetration(store, "efficiency", key, config))

    # 2. Congestion by zone
    if store.has_congestion_data():
        for key in CONGESTION_KEYS:
            spec = _metric_spec(key)
            panels = [(_zone_label(z), ("congestion", z, key)) for z in CONGESTION_ZONE_ORDER]
            artifacts.extend(
                _plot_penetration_grid(
                    store,
                    panels,
                    title=f"{spec.label} by congestion zone",
                    ylabel=spec.ylabel,
                    stem=f"congestion_{key}_by_zone",
                    config=config,
                )
            )

    # 3. Stability
    for key in STABILITY_KEYS:
        spec = _metric_spec(key)
        panels = [
            (phase.replace("_", " ").title(), ("stability", phase, key))
            for phase in STABILITY_PHASES
        ]
        artifacts.extend(
            _plot_penetration_grid(
                store,
                panels,
                title=f"{spec.label} by incident phase",
                ylabel=spec.ylabel,
                stem=f"stability_{key}_by_phase",
                config=config,
                ncols=3,
                figsize_per_cell=(5.0, 5.0),
                sharey=True,
            )
        )

    # 4. Temporal series of mean speed
    artifacts.extend(
        _plot_timeseries_by_penetration(
            store,
            filename="metrics_stability_by_step.csv",
            x_col="time",
            y_col="mean_speed_mps",
            title="Mean speed over time - 60 s moving average",
            ylabel=_metric_spec("mean_speed_mps").ylabel,
            stem="metrics_mean_speed_by_penetration",
            config=config,
            incident_window=incident_window,
            smooth_window_s=60.0,
        )
    )

    # 5. Temporal series of congestion metrics by zone
    for zone in store.discover_congestion_zones():
        z_label = _zone_label(zone)
        for key in CONGESTION_TIMESERIES_KEYS:
            spec = _metric_spec(key)
            artifacts.extend(
                _plot_timeseries_by_penetration(
                    store,
                    filename=f"metrics_congestion_{zone}_by_interval.csv",
                    x_col="interval_midpoint_s",
                    y_col=key,
                    title=f"{spec.label} over time - {z_label}",
                    ylabel=spec.ylabel,
                    stem=f"metrics_congestion_{key}_{zone}_by_penetration",
                    config=config,
                    incident_window=incident_window,
                    with_markers=True,
                )
            )

    _cleanup_stale_svgs(output_path, artifacts)
    report_path = _write_report(output_path, artifacts, manifest)
    return [a.path for a in artifacts] + [report_path]