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
    current_time = 0.0
    incident_started = False
    try:
        while traci.simulation.getMinExpectedNumber() > 0 and current_time < duration:
            current_time = traci.simulation.getTime()
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


def run_from_manifest(manifest_file: str | Path, strategy: str) -> Path:
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
    detector_tree = ET.parse(Path(manifest["detectors"]).resolve())
    detector_output = output_directory / "e2_output.xml"
    for detector in detector_tree.getroot().iter("laneAreaDetector"):
        detector.set("file", str(detector_output))

    temporary_detector = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".add.xml", dir=output_directory, delete=False
    )
    try:
        detector_tree.write(
            temporary_detector, encoding="utf-8", xml_declaration=True
        )
        temporary_detector.close()
        run_simulation(
            duration=duration,
            incident_edge=str(incident["edge"]),
            incident_start=float(incident["begin_s"]),
            incident_end=float(incident["end_s"]),
            blocked_lane_index=int(incident.get("blocked_lane", 0)),
            sumo_file=str(Path(manifest["sumocfg"]).resolve()),
            output_dir=output_directory,
            additional_file=temporary_detector.name,
        )
    finally:
        temporary_detector.close()
        Path(temporary_detector.name).unlink(missing_ok=True)

    return output_directory


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run one experiment strategy")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--strategy", required=True, choices=("m0", "m1", "m2", "m3"))
    args = parser.parse_args()
    run_from_manifest(args.manifest, args.strategy)
