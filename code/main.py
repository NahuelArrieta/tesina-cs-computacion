from simulation.simulator import run_simulation
import os

INCIDENT_EDGE = "A2B2" 
SIM_DURATION = 1000.0  
BLOCKED_LANE_INDEX = 0          
INCIDENT_START = 100.0          
INCIDENT_END = 600.0 
NETWORKS_DIR = "./networks/"
SUMO_FILE = "synthetic/synthetic.sumocfg"
OUTPUTS_DIR = "./output/"
OUTPUT_DIR = os.path.join(OUTPUTS_DIR, "synthetic")

sumo_file_path = os.path.join(NETWORKS_DIR, SUMO_FILE)

run_simulation(SIM_DURATION, INCIDENT_EDGE, INCIDENT_START, INCIDENT_END, sumo_file_path, OUTPUT_DIR)

## Compute efficiency metrics
from metrics.efficiency_metrics import parse_tripinfo, compute_network_efficiency
tripinfo_path = os.path.join(OUTPUT_DIR, "tripinfo.xml")
df_trips = parse_tripinfo(tripinfo_path, exclude_ids=["veh_bloqueo"])
efficiency_metrics = compute_network_efficiency(df_trips)
print("Efficiency Metrics:")
for metric, value in efficiency_metrics.items():
    print(f"{metric}: {value}")