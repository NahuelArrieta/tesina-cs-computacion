import os
import sys
import traci
from incident.incident_manager import IncidentManager

INCIDENT_EDGE = "A2B2"   
BLOCKED_LANE_INDEX = 0          
INCIDENT_START = 100.0          
INCIDENT_END = 600.0 
SUMO_FILE = "./networks/synthetic/synthetic.sumocfg"

if "SUMO_HOME" in os.environ:
    tools = os.path.join(os.environ["SUMO_HOME"], "tools")
    sys.path.append(tools)
else:
    sys.exit("Declara la variable de entorno SUMO_HOME")

sumo_binary = "sumo-gui"
sumo_cmd = [sumo_binary, "-c", SUMO_FILE, "--step-length", "0.1"]


traci.start(sumo_cmd)

incident = IncidentManager()

while traci.simulation.getMinExpectedNumber() > 0:
    current_time = traci.simulation.getTime()

    if current_time == INCIDENT_START:
        incident.start(INCIDENT_EDGE, BLOCKED_LANE_INDEX)

    if current_time == INCIDENT_END:
        incident.end()

    traci.simulationStep()

traci.close()