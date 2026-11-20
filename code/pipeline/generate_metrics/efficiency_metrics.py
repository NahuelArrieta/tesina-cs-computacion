import os
import xml.etree.ElementTree as ET
import pandas as pd

def parse_tripinfo(xml_file_path, exclude_ids):
    if not os.path.exists(xml_file_path):
        raise FileNotFoundError(f"File not found: {xml_file_path}")

    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    records = []
    for trip in root.findall("tripinfo"):
        veh_id = trip.get("id")
        
        if veh_id in exclude_ids:
            continue

        records.append({
            "veh_id": veh_id,
            "duration": float(trip.get("duration")),
            "timeLoss": float(trip.get("timeLoss")),
            "routeLength": float(trip.get("routeLength")),
            "depart": float(trip.get("depart")),
            "arrival": float(trip.get("arrival")),
            "waitingTime": float(trip.get("waitingTime", 0.0))
        })

    return pd.DataFrame(records)


def compute_network_efficiency(df_trips, sim_duration_seconds=3600.0):
    n_completed = len(df_trips)
    if n_completed == 0:
        return {
            "completed_vehicles": 0,
            "total_travel_time_s": 0.0,
            "mean_travel_time_s": 0.0,
            "total_delay_s": 0.0,
            "mean_delay_s": 0.0,
            "mean_speed_mps": 0.0,
            "throughput_veh_hour": 0.0
        }

    total_travel_time = df_trips["duration"].sum()
    total_delay = df_trips["timeLoss"].sum()
    total_distance = df_trips["routeLength"].sum()

    mean_travel_time = total_travel_time / n_completed
    mean_delay = total_delay / n_completed
    mean_speed = total_distance / total_travel_time if total_travel_time > 0 else 0.0
    throughput_per_hour = (n_completed / sim_duration_seconds) * 3600.0

    return {
        "completed_vehicles": int(n_completed),
        "total_travel_time_s": round(total_travel_time, 2),
        "mean_travel_time_s": round(mean_travel_time, 2),
        "total_delay_s": round(total_delay, 2),
        "mean_delay_s": round(mean_delay, 2),
        "mean_speed_mps": round(mean_speed, 2),
        "throughput_veh_hour": round(throughput_per_hour, 2)
    }
