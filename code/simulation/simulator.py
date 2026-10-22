import os
import sys
import traci
from .incident_manager import IncidentManager

## Output files
TRIPINFO_PATH = "tripinfo.xml"

def run_simulation(duration, incident_edge, incident_start, incident_end, sumo_file, output_dir=None):
    sumo_binary = "sumo-gui"

    if "SUMO_HOME" in os.environ:
        tools = os.path.join(os.environ["SUMO_HOME"], "tools")
        sys.path.append(tools)
    else:
        sys.exit("Declare the SUMO_HOME environment variable")

    sumo_cmd = [sumo_binary, "-c", sumo_file, "--step-length", "0.1"]

    if output_dir:
        # Check if the output directory exists, if not create it
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        sumo_cmd += ["--tripinfo-output", os.path.join(output_dir, TRIPINFO_PATH)]

    traci.start(sumo_cmd)

    incident = IncidentManager()
    current_time = 0.0

    while traci.simulation.getMinExpectedNumber() > 0 and current_time < duration:
        current_time = traci.simulation.getTime()

        if current_time == incident_start:
            incident.start(incident_edge, 0)

        if current_time == incident_end:
            incident.end()

        traci.simulationStep()

    traci.close()
