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

## Compute stability metrics
from metrics.stability_metrics import parse_and_compute_phased_stability
fcd_output_path = os.path.join(OUTPUT_DIR, "fcd_output.xml")
phase_windows = {
    "pre_incident": (0.0, INCIDENT_START),
    "incident": (INCIDENT_START, INCIDENT_END),
    "post_incident": (INCIDENT_END, SIM_DURATION)
}
steps_results, stability_metrics = parse_and_compute_phased_stability(fcd_output_path, phase_windows, exclude_ids=["veh_bloqueo"])
print("\nStability Metrics:")
for phase, metrics in stability_metrics.items():
    print(f"\nPhase: {phase}")
    for metric, value in metrics.items():
        print(f"\t{metric}: {value}") 
step = steps_results[43] if steps_results else None
if step:
    print("\nStability Steps Results:")
    print(step)

## Compute congestion metrics
from metrics.congestion_metrics import parse_and_compute_congestion_e2
e2_output_path = os.path.join(OUTPUT_DIR, "e2_output.xml")
detector_ids = ["e2_A2B2_0", "e2_A1A2_0", "e2_B1B2_0"]
congestion_metrics, timeseries_records = parse_and_compute_congestion_e2(
    e2_xml_path=e2_output_path,
    incident_start_s=INCIDENT_START,
    incident_end_s=INCIDENT_END,
    target_detector_ids=detector_ids,
    congested_queue_threshold_m=20.0,
    baseline_speed_ratio=0.90
)
print("\nCongestion Metrics:")
for metric, value in congestion_metrics.items():
    print(f"{metric}: {value}") 

## Compute timeseries records
record = timeseries_records[0] if timeseries_records else None
if record:
    print("\nTimeseries Records:")
    print(record) 