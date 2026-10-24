from simulation.simulator import run_simulation
from metrics.metrics_handler import process_metrics
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
RESULTS_DIR = "../results"
RESULT_NAME = "synthetic"

sumo_file_path = os.path.join(NETWORKS_DIR, SUMO_FILE)

run_simulation(SIM_DURATION, INCIDENT_EDGE, INCIDENT_START, INCIDENT_END, sumo_file_path, OUTPUT_DIR)

## Export metrics
process_metrics(
    output_dir=OUTPUT_DIR,
    export_dir=RESULTS_DIR,
    name=RESULT_NAME,
    incident_start_s=INCIDENT_START,
    incident_end_s=INCIDENT_END,
    sim_duration_seconds=SIM_DURATION,
    exclude_ids=["veh_bloqueo"],
    target_detector_ids=["e2_A2B2_0", "e2_A1A2_0", "e2_B1B2_0"],
)
