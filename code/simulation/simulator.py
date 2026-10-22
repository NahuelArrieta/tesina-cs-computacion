import os
import sys
import traci
from .incident_manager import IncidentManager

def run_simulation(incident_edge, blocked_lane_index, incident_start, incident_end, sumo_file):
    sumo_binary = "sumo-gui"

    if "SUMO_HOME" in os.environ:
        tools = os.path.join(os.environ["SUMO_HOME"], "tools")
        sys.path.append(tools)
    else:
        sys.exit("Declara la variable de entorno SUMO_HOME")

    sumo_cmd = [sumo_binary, "-c", sumo_file, "--step-length", "0.1"]

    traci.start(sumo_cmd)

    incident = IncidentManager()

    while traci.simulation.getMinExpectedNumber() > 0:
        current_time = traci.simulation.getTime()

        if current_time == incident_start:
            incident.start(incident_edge, blocked_lane_index)

        if current_time == incident_end:
            incident.end()

        traci.simulationStep()

    traci.close()
