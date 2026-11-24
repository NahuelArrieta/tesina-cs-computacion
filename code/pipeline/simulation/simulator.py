import csv
import os
import sys
import json
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence
import traci

from strategies.main import get_strategy
try:
    from .incident_manager import IncidentManager
except ImportError:
    from incident_manager import IncidentManager

## Output files
TRIPINFO_PATH = "tripinfo.xml"
FCD_OUTPUT_PATH = "fcd_output.xml"
COMPUTATION_TIME_PATH = "computation_time.csv"
DEFAULT_STEP_LENGTH_S = 0.1


def export_computation_times(
    output_dir: str | Path,
    computation_times: Sequence[tuple[float, float]],
) -> Path:
    """Write per-step strategy execution times to a CSV file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    computation_time_file = output_path / COMPUTATION_TIME_PATH
    with computation_time_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("time", "execution_time_s"))
        for sim_time, elapsed_s in computation_times:
            writer.writerow((sim_time, f"{elapsed_s:.9f}"))
    return computation_time_file


def run_simulation(
    duration,
    incident_edge,
    incident_start,
    incident_end,
    sumo_file,
    output_dir=None,
    blocked_lane_index=0,
    additional_file=None,
    subgraph_file=None,
    visualization_interval_s=10.0,
    show_occupancy_overlay=False,
    seed=None,
    strategy=None,
):
    sumo_binary = os.environ.get("SUMO_BINARY", "sumo")

    if "SUMO_HOME" in os.environ:
        tools = os.path.join(os.environ["SUMO_HOME"], "tools")
        sys.path.append(tools)
    else:
        sys.exit("Declare the SUMO_HOME environment variable")

    sumo_cmd = [
        sumo_binary,
        "-c",
        sumo_file,
        "--no-step-log",
        "--no-warnings",
        "--duration-log.disable",
    ]
    if additional_file:
        sumo_cmd += ["--additional-files", str(additional_file)]
    if seed is not None:
        sumo_cmd += ["--seed", str(seed)]

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.abspath(output_dir)
        sumo_cmd += ["--tripinfo-output", os.path.join(output_path, TRIPINFO_PATH)]

        sumo_cmd += ["--fcd-output", os.path.join(output_path, FCD_OUTPUT_PATH),
            "--fcd-output.attributes", "id,speed,acceleration",
        ]

    traci.start(sumo_cmd)
    incident = IncidentManager()
    visualizer = None
    if subgraph_file:
        from utils.dual_graph_handler import load_dual_graph
        try:
            from .subgraph_visualization import SubgraphMonitor, SumoGuiOverlay
        except ImportError:
            from subgraph_visualization import SubgraphMonitor, SumoGuiOverlay

        subgraph = load_dual_graph(str(subgraph_file)).copy()
        visualizer = SumoGuiOverlay(
            subgraph, incident_edge, show_occupancy_overlay
        )
        monitor = SubgraphMonitor(subgraph) if show_occupancy_overlay else None
    current_time = 0.0
    incident_started = False
    next_visualization_s = 0.0
    computation_times: list[tuple[float, float]] = []
    try:
        while traci.simulation.getMinExpectedNumber() > 0 and current_time < duration:
            current_time = traci.simulation.getTime()
            if visualizer and current_time >= next_visualization_s:
                if monitor:
                    visualizer.update(monitor.sample())
                next_visualization_s += visualization_interval_s
            if current_time >= incident_start and not incident_started:
                incident.start(incident_edge, blocked_lane_index)
                incident_started = True
            if current_time >= incident_end and incident.is_active:
                incident.end()

            if strategy is not None:
                start_s = time.perf_counter()
                strategy.execute()
                elapsed_s = time.perf_counter() - start_s
                computation_times.append((round(current_time, 6), elapsed_s))

            traci.simulationStep()

        if output_dir:
            export_computation_times(output_path, computation_times)
    finally:
        if incident.is_active:
            incident.end()
        traci.close()
        if visualizer:
            visualizer.close()
        print(f"Simulation finished at time {current_time:.2f} seconds.")


def run_from_manifest(
    manifest_file: str | Path,
    strategy: str,
    penetration: float,
    seed: int,
    visualization_mode: str | None = None,
) -> Path:
    """Run one strategy and penetration using an experiment manifest."""
    manifest_path = Path(manifest_file).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    experiment_directory = manifest_path.parent
    output_directory = Path(
        manifest.get("output_directory", experiment_directory / "output")
    ).resolve() / f"p{int(round(penetration * 100))}" / strategy / f"seed_{seed}"
    output_directory.mkdir(parents=True, exist_ok=True)
    incident = manifest["incident"]
    duration = float(manifest["end_s"])
    visualization_interval_s = float(
        manifest.get("visualization_interval_s", 10.0)
    )
    if visualization_interval_s <= 0.0:
        raise ValueError("simulation.visualization_interval_s must be positive")
    configured_visualization = manifest.get("visualization", False)
    if visualization_mode is None:
        visualization_mode = (
            "gui-overlay"
            if configured_visualization is True
            else configured_visualization
            if isinstance(configured_visualization, str)
            else None
        )
    valid_modes = {None, "gui-overlay"}
    if visualization_mode not in valid_modes:
        raise ValueError(
            "visualization_mode must be None or 'gui-overlay'"
        )
    if visualization_mode == "gui-overlay" and Path(
        os.environ.get("SUMO_BINARY", "sumo")
    ).name != "sumo-gui":
        raise ValueError(
            "--gui-overlay requires SUMO_BINARY=sumo-gui"
        )
    detectors_file = experiment_directory / "artifacts" / "detectors.add.xml"
    subgraph_file = experiment_directory / "artifacts" / "subgraph.graphml"
    if not detectors_file.is_file():
        raise FileNotFoundError(f"Detector file not found: {detectors_file}")
    detector_tree = ET.parse(detectors_file)
    detector_output = output_directory / "e2_output.xml"
    for detector in detector_tree.getroot().iter("laneAreaDetector"):
        detector.set("file", str(detector_output))

    temporary_config = None
    temporary_detector = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".add.xml", dir=output_directory, delete=False
    )
    try:
        detector_tree.write(
            temporary_detector, encoding="utf-8", xml_declaration=True
        )
        temporary_detector.close()
        network_file = Path(
            os.environ.get(
                "NETWORK_DIR",
                str(manifest_path.parents[2] / "source files" / "networks"),
            )
        ).expanduser().resolve() / str(manifest["network"])
        routes_directory = experiment_directory / "routes"
        percentage = int(round(penetration * 100))
        route_files = [
            routes_directory / "routes.rou.xml",
            routes_directory / f"penetration_{percentage}.rou.xml",
        ]
        for route_file in [network_file, *route_files]:
            if not route_file.is_file():
                raise FileNotFoundError(f"Simulation input file not found: {route_file}")
        sumo_config_tree = ET.Element("configuration")
        input_node = ET.SubElement(sumo_config_tree, "input")
        ET.SubElement(input_node, "net-file", {"value": str(network_file)})
        ET.SubElement(
            input_node,
            "route-files",
            {"value": ",".join(str(route_file) for route_file in route_files)},
        )
        ET.SubElement(
            input_node,
            "additional-files",
            {"value": temporary_detector.name},
        )
        time_node = ET.SubElement(sumo_config_tree, "time")
        ET.SubElement(time_node, "begin", {"value": str(manifest["begin_s"])})
        ET.SubElement(time_node, "end", {"value": str(manifest["end_s"])})
        ET.SubElement(
            time_node,
            "step-length",
            {"value": str(DEFAULT_STEP_LENGTH_S)},
        )
        ET.indent(sumo_config_tree, space="    ")
        temporary_config = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".sumocfg", dir=output_directory, delete=False
        )
        ET.ElementTree(sumo_config_tree).write(
            temporary_config, encoding="utf-8", xml_declaration=True
        )
        temporary_config.close()

        print(
            f"Running simulation for strategy '{strategy}', penetration {penetration:g}, seed {seed}..."
        )

        strategy = get_strategy(strategy_name=strategy, config={})

        run_simulation(
            duration=duration,
            incident_edge=str(incident["edge"]),
            incident_start=float(incident["begin_s"]),
            incident_end=float(incident["end_s"]),
            blocked_lane_index=int(incident.get("blocked_lane", 0)),
            sumo_file=temporary_config.name,
            output_dir=output_directory,
            subgraph_file=(
                str(subgraph_file)
                if Path(os.environ.get("SUMO_BINARY", "sumo")).name == "sumo-gui"
                else None
            ),
            visualization_interval_s=visualization_interval_s,
            show_occupancy_overlay=visualization_mode == "gui-overlay",
            seed=seed,
            strategy=strategy
        )
    finally:
        temporary_detector.close()
        Path(temporary_detector.name).unlink(missing_ok=True)
        if temporary_config is not None:
            temporary_config.close()
            Path(temporary_config.name).unlink(missing_ok=True)

    return output_directory
