import os
import sys
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import traci
from .incident_manager import IncidentManager

## Output files
TRIPINFO_PATH = "tripinfo.xml"
FCD_OUTPUT_PATH = "fcd_output.xml"


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
    step_length_s=0.1,
    visualization_mode=None,
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
        from .subgraph_visualization import SubgraphVisualizer

        visualizer = SubgraphVisualizer(
            load_dual_graph(str(subgraph_file)).copy(),
            step_length_s,
            sumo_gui=visualization_mode == "gui-overlay",
        )
    current_time = 0.0
    incident_started = False
    next_visualization_s = 0.0
    try:
        while traci.simulation.getMinExpectedNumber() > 0 and current_time < duration:
            current_time = traci.simulation.getTime()
            if visualizer and current_time >= next_visualization_s:
                visualizer.update(current_time)
                next_visualization_s += visualization_interval_s
            if visualizer and not visualizer.wait_for_next_step():
                visualizer.close()
                visualizer = None
            if current_time >= incident_start and not incident_started:
                incident.start(incident_edge, blocked_lane_index)
                incident_started = True
            if current_time >= incident_end and incident.is_active:
                incident.end()
            traci.simulationStep()
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
    visualization_mode: str | None = None,
) -> Path:
    """Run one strategy using an experiment manifest and save raw outputs."""
    manifest_path = Path(manifest_file).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    experiment_directory = Path(
        manifest.get("experiment_directory", manifest_path.parent)
    ).resolve()
    output_directory = Path(
        manifest.get("output_directory", experiment_directory / "output")
    ).resolve() / strategy
    output_directory.mkdir(parents=True, exist_ok=True)

    incident = manifest["incident"]
    simulation = manifest.get("simulation", {})
    duration = float(simulation.get("end_s", 3600.0))
    visualization_interval_s = float(
        simulation.get("visualization_interval_s", 10.0)
    )
    if visualization_interval_s <= 0.0:
        raise ValueError("simulation.visualization_interval_s must be positive")
    step_length_s = float(simulation.get("step_length_s", 0.1))
    if step_length_s <= 0.0:
        raise ValueError("simulation.step_length_s must be positive")
    configured_visualization = simulation.get("visualization", False)
    if visualization_mode is None:
        visualization_mode = (
            "gui-overlay"
            if configured_visualization is True
            else configured_visualization
            if isinstance(configured_visualization, str)
            else None
        )
    valid_modes = {None, "gui-overlay", "graph-window"}
    if visualization_mode not in valid_modes:
        raise ValueError(
            "visualization_mode must be None, 'gui-overlay', or 'graph-window'"
        )
    if visualization_mode == "gui-overlay" and Path(
        os.environ.get("SUMO_BINARY", "sumo")
    ).name != "sumo-gui":
        raise ValueError(
            "--gui-overlay requires SUMO_BINARY=sumo-gui; use "
            "--graph-window with SUMO_BINARY=sumo"
        )
    detector_tree = ET.parse(Path(manifest["detectors"]).resolve())
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
        sumo_config_tree = ET.parse(Path(manifest["sumocfg"]).resolve())
        additional_files = sumo_config_tree.find("./input/additional-files")
        if additional_files is None:
            raise ValueError("SUMO configuration is missing input/additional-files")
        additional_paths = [
            path
            for path in additional_files.get("value", "").split(",")
            if Path(path).resolve() != Path(manifest["detectors"]).resolve()
        ]
        additional_paths.insert(0, temporary_detector.name)
        additional_files.set("value", ",".join(additional_paths))
        temporary_config = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".sumocfg", dir=output_directory, delete=False
        )
        sumo_config_tree.write(
            temporary_config, encoding="utf-8", xml_declaration=True
        )
        temporary_config.close()
        run_simulation(
            duration=duration,
            incident_edge=str(incident["edge"]),
            incident_start=float(incident["begin_s"]),
            incident_end=float(incident["end_s"]),
            blocked_lane_index=int(incident.get("blocked_lane", 0)),
            sumo_file=temporary_config.name,
            output_dir=output_directory,
            subgraph_file=manifest["subgraph"] if visualization_mode else None,
            visualization_mode=visualization_mode,
            visualization_interval_s=visualization_interval_s,
            step_length_s=step_length_s,
        )
    finally:
        temporary_detector.close()
        Path(temporary_detector.name).unlink(missing_ok=True)
        if temporary_config is not None:
            temporary_config.close()
            Path(temporary_config.name).unlink(missing_ok=True)

    return output_directory


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run one experiment strategy")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--strategy", required=True, choices=("m0", "m1", "m2", "m3"))
    visualization_group = parser.add_mutually_exclusive_group()
    visualization_group.add_argument(
        "--gui-overlay",
        action="store_const",
        const="gui-overlay",
        dest="visualization_mode",
        help="Color the subgraph streets as overlays in SUMO-GUI.",
    )
    visualization_group.add_argument(
        "--graph-window",
        action="store_const",
        const="graph-window",
        dest="visualization_mode",
        help="Open the separate live dual-graph window.",
    )
    args = parser.parse_args()
    run_from_manifest(
        args.manifest,
        args.strategy,
        visualization_mode=args.visualization_mode,
    )
