import csv
import json
import os
import networkx as Nx
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from utils.dual_graph_handler import load_dual_graph
from utils.subgraph_extractor import get_zones
from .congestion_metrics import parse_and_compute_congestion_e2
from .efficiency_metrics import compute_network_efficiency, parse_tripinfo
from .stability_metrics import parse_and_compute_phased_stability


MetricData = dict[str, Any]


def collect_metrics(
    incident_edge: str,
    output_dir: str | Path,
    incident_start_s: float,
    incident_end_s: float,
    sim_duration_seconds: float,
    graph: Nx.DiGraph,
    exclude_ids: Iterable[str] = (),
    congested_queue_threshold_m: float = 20.0,
    baseline_speed_ratio: float = 0.90,
) -> MetricData:
    """Compute all metrics from the XML files produced by a simulation.

    ``output_dir`` must contain ``tripinfo.xml``, ``fcd_output.xml`` and
    ``e2_output.xml``. Missing files are reported by the underlying parsers.
    """
    output_path = Path(output_dir)
    excluded = set(exclude_ids)
    phase_windows = {
        "pre_incident": (0.0, incident_start_s),
        "incident": (incident_start_s, incident_end_s),
        "post_incident": (incident_end_s, sim_duration_seconds),
    }

    trips = parse_tripinfo(output_path / "tripinfo.xml", excluded)
    efficiency = compute_network_efficiency(trips, sim_duration_seconds)
    stability_steps, stability = parse_and_compute_phased_stability(
        output_path / "fcd_output.xml",
        phase_windows,
        excluded,
    )

    zone_streets = get_zones(graph, incident_edge=incident_edge)

    congestion_per_zone, congestion_timeseries = parse_and_compute_congestion_e2(
        output_path / "e2_output.xml",
        incident_start_s,
        incident_end_s,
        zone_streets,
        congested_queue_threshold_m,
        baseline_speed_ratio,
    )

    return {
        "efficiency": efficiency,
        "stability": stability,
        "stability_timeseries": stability_steps,
        "congestion": congestion_per_zone,
        "congestion_timeseries": congestion_timeseries["other_zones"]
    }


def _write_rows(
    rows: Sequence[Mapping[str, Any]],
    path: Path,
    first_columns: Sequence[str] = (),
) -> None:
    """Write a collection of metric records to a CSV file."""
    columns = {key for row in rows for key in row}
    fieldnames = [
        *[column for column in first_columns if column in columns],
        *sorted(columns.difference(first_columns)),
    ]
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_metrics(
    metrics: Mapping[str, Any],
    export_dir: str | Path,
    name: str = "default",
    basename: str = "metrics",
) -> dict[str, Path]:
    """Export summaries and time series under ``<export_dir>/<name>``."""
    destination = Path(export_dir) / name
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / f"{basename}.json"

    aggregated = {
        key: value
        for key, value in metrics.items()
        if not key.endswith("_timeseries")
    }
    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(aggregated, json_file, indent=2, ensure_ascii=False)
        json_file.write("\n")

    output_paths = {"json": json_path}
    series_files = {
        "stability_timeseries": (
            f"{basename}_stability_by_step.csv",
            ("time",),
        ),
        "congestion_timeseries": (
            f"{basename}_congestion_by_interval.csv",
            ("time_begin_s", "time_end_s", "interval_midpoint_s"),
        ),
    }
    for series_name, (filename, first_columns) in series_files.items():
        path = destination / filename
        rows = metrics.get(series_name, [])
        if not isinstance(rows, list):
            raise TypeError(f"{series_name} must be a list of row records")
        _write_rows(rows, path, first_columns)
        output_paths[series_name] = path

    return output_paths


def process_metrics(
    incident_edge: str,
    output_dir: str | Path,
    incident_start_s: float,
    incident_end_s: float,
    sim_duration_seconds: float,
    export_dir: str | Path | None = None,
    name: str = "default",
    basename: str = "metrics",
    exclude_ids: Iterable[str] = (),
    congested_queue_threshold_m: float = 20.0,
    baseline_speed_ratio: float = 0.90,
) -> tuple[MetricData, dict[str, Path]]:
    """Compute all metrics and export them, returning data and output paths."""
    graph = load_dual_graph(os.path.join(output_dir, "graph.graphml"))

    metrics = collect_metrics(
        incident_edge=incident_edge,
        output_dir=output_dir,
        incident_start_s=incident_start_s,
        incident_end_s=incident_end_s,
        sim_duration_seconds=sim_duration_seconds,
        graph=graph,
        exclude_ids=exclude_ids,
        congested_queue_threshold_m=congested_queue_threshold_m,
        baseline_speed_ratio=baseline_speed_ratio,
    )
    destination = output_dir if export_dir is None else export_dir
    return metrics, export_metrics(metrics, destination, name, basename)
