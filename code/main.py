from simulation.simulator import run_simulation
from metrics.metrics_handler import process_metrics
from utils.dual_graph_handler import load_dual_graph, export_dual_graph
from utils.subgraph_extractor import extract_upstream_subgraph
import os

INCIDENT_EDGE = "A2B2" 
SIM_DURATION = 1000.0  
BLOCKED_LANE_INDEX = 0          
INCIDENT_START = 100.0          
INCIDENT_END = 600.0 
NETWORKS_DIR = "./networks/synthetic/"
SUMO_FILE = "synthetic.sumocfg"
OUTPUTS_DIR = "./output/"
OUTPUT_DIR = os.path.join(OUTPUTS_DIR, "synthetic")
RESULTS_DIR = "../results"
RESULT_NAME = "synthetic"



sumo_file_path = os.path.join(NETWORKS_DIR, SUMO_FILE)

graph = load_dual_graph(os.path.join(NETWORKS_DIR, "graph.graphml"))

subgraph = extract_upstream_subgraph(
    graph=graph,
    incident_edge=INCIDENT_EDGE,
    min_prob_threshold=0.05,
    max_seconds_travel=100.0
)

# export_dual_graph(subgraph, os.path.join(OUTPUT_DIR, "subgraph.graphml"))

# run_simulation(SIM_DURATION, INCIDENT_EDGE, INCIDENT_START, INCIDENT_END, sumo_file_path, OUTPUT_DIR)

## Export metrics
process_metrics(
    incident_edge=INCIDENT_EDGE,
    output_dir=OUTPUT_DIR,
    export_dir=RESULTS_DIR,
    name=RESULT_NAME,
    incident_start_s=INCIDENT_START,
    incident_end_s=INCIDENT_END,
    sim_duration_seconds=SIM_DURATION,
    exclude_ids=["veh_bloqueo"],
)
