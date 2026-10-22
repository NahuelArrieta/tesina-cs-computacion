import os
import xml.etree.ElementTree as ET
import numpy as np

HARD_BRAKE_THRESHOLD=-4.0

class PhaseAccumulator:
    """Helper class to collect vehicle kinematics within a specific temporal phase."""
    def __init__(self, name, start_time, end_time):
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.speed_std_series = []
        self.accel_var_series = []
        self.mean_speed_series = []
        self.hard_brake_events = 0
        self.total_samples = 0

    def contains(self, timestamp):
        return self.start_time <= timestamp < self.end_time

    def add_step(self, speeds, accelerations, hard_brakes):
        if speeds:
            self.speed_std_series.append(float(np.std(speeds)))
            self.mean_speed_series.append(float(np.mean(speeds)))
        if accelerations:
            self.accel_var_series.append(float(np.var(accelerations)))
        self.hard_brake_events += hard_brakes
        self.total_samples += len(speeds)

    def compute_summary(self):
        return {
            "mean_speed_std": round(float(np.mean(self.speed_std_series)), 4) if self.speed_std_series else 0.0,
            "max_speed_std": round(float(np.max(self.speed_std_series)), 4) if self.speed_std_series else 0.0,
            "mean_accel_var": round(float(np.mean(self.accel_var_series)), 4) if self.accel_var_series else 0.0,
            "max_accel_var": round(float(np.max(self.accel_var_series)), 4) if self.accel_var_series else 0.0,
            "mean_speed_mps": round(float(np.mean(self.mean_speed_series)), 4) if self.mean_speed_series else 0.0,
            "hard_brake_events": self.hard_brake_events,
            "hard_brake_ratio": round(self.hard_brake_events / self.total_samples, 6) if self.total_samples > 0 else 0.0,
        }


def parse_and_compute_phased_stability(xml_file_path, phase_windows, exclude_ids):
    if not os.path.exists(xml_file_path):
        raise FileNotFoundError(f"File not found: {xml_file_path}")

    # Initialize accumulators
    phases = [
        PhaseAccumulator(phase_name, window[0], window[1])
        for phase_name, window in phase_windows.items()
    ]

    min_time = min(w[0] for w in phase_windows.values())
    max_time = max(w[1] for w in phase_windows.values())

    context = ET.iterparse(xml_file_path, events=("end",))

    for event, elem in context:
        if elem.tag == "timestep":
            step_time = float(elem.get("time"))

            # Discard steps falling outside all defined analysis phases
            if step_time < min_time or step_time >= max_time:
                elem.clear()
                continue

            speeds = []
            accelerations = []
            hard_brakes = 0

            for veh in elem.findall("vehicle"):
                veh_id = veh.get("id")
                if veh_id in exclude_ids:
                    continue

                speed = float(veh.get("speed", 0.0))
                accel = float(veh.get("acceleration", 0.0))

                speeds.append(speed)
                accelerations.append(accel)

                if accel <= HARD_BRAKE_THRESHOLD:
                    hard_brakes += 1

            # Dispatch step values to the matching phase
            for phase in phases:
                if phase.contains(step_time):
                    phase.add_step(speeds, accelerations, hard_brakes)
                    break

            elem.clear()

    del context

    # Consolidate results per phase
    results = {}
    for phase in phases:
        results[phase.name] = phase.compute_summary()

    return results