from simulation.simulator import run_simulation
import os

INCIDENT_EDGE = "A2B2"   
BLOCKED_LANE_INDEX = 0          
INCIDENT_START = 100.0          
INCIDENT_END = 600.0 
NETWORKS_DIR = "./networks/"
SUMO_FILE = "synthetic/synthetic.sumocfg"

sumo_file_path = os.path.join(NETWORKS_DIR, SUMO_FILE)

run_simulation(INCIDENT_EDGE, BLOCKED_LANE_INDEX, INCIDENT_START, INCIDENT_END, sumo_file_path)