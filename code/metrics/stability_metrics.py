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
        self.jerk_samples = []
        self.hard_brake_events = 0
        self.total_samples = 0

    def contains(self, timestamp):
        return self.start_time <= timestamp < self.end_time

    def add_step(self, speeds, accelerations, jerks, hard_brakes):
        if speeds:
            self.speed_std_series.append(float(np.std(speeds)))
            self.mean_speed_series.append(float(np.mean(speeds)))
        if accelerations:
            self.accel_var_series.append(float(np.var(accelerations)))
        if jerks:
            self.jerk_samples.append(float(np.mean(jerks)))
        self.hard_brake_events += hard_brakes
        self.total_samples += len(speeds)

    def compute_summary(self):
        abs_jerks = np.abs(self.jerk_samples) if self.jerk_samples else []  
        return {
            "mean_speed_std": round(float(np.mean(self.speed_std_series)), 4) if self.speed_std_series else 0.0,
            "max_speed_std": round(float(np.max(self.speed_std_series)), 4) if self.speed_std_series else 0.0,
            "mean_accel_var": round(float(np.mean(self.accel_var_series)), 4) if self.accel_var_series else 0.0,
            "max_accel_var": round(float(np.max(self.accel_var_series)), 4) if self.accel_var_series else 0.0,
            "mean_speed_mps": round(float(np.mean(self.mean_speed_series)), 4) if self.mean_speed_series else 0.0,
            "hard_brake_events": self.hard_brake_events,
            "hard_brake_ratio": round(self.hard_brake_events / self.total_samples, 6) if self.total_samples > 0 else 0.0,
            "mean_abs_jerk_mps3": round(float(np.mean(abs_jerks)), 4) if len(abs_jerks) > 0 else 0.0,  # <--- NUEVO
            "max_abs_jerk_mps3": round(float(np.max(abs_jerks)), 4) if len(abs_jerks) > 0 else 0.0,   # <--- NUEVO
            "hard_brake_events": self.hard_brake_events
        }

def compute_steps_stability(xml_file_path, exclude_ids):
    context = ET.iterparse(xml_file_path, events=("end",))

    results = []
    
    veh_prev_state = {}

    for event, elem in context:
        if elem.tag == "timestep":
            step_time = float(elem.get("time"))

            speeds = []
            accelerations = []
            jerks_step = []
            hard_brakes = 0

            for veh in elem.findall("vehicle"):
                veh_id = veh.get("id")
                if veh_id in exclude_ids:
                    continue

                speed = float(veh.get("speed", 0.0))
                accel = float(veh.get("acceleration", 0.0))

                if veh_id in veh_prev_state:
                    prev_time, prev_accel = veh_prev_state[veh_id]
                    dt = step_time - prev_time
                    if dt > 0:
                        jerk = (accel - prev_accel) / dt
                        jerks_step.append(jerk)

                veh_prev_state[veh_id] = (step_time, accel)

                speeds.append(speed)
                accelerations.append(accel)

                if accel <= HARD_BRAKE_THRESHOLD:
                    hard_brakes += 1

            results.append({
                "time": step_time,
                "speeds": speeds,
                "accelerations": accelerations,
                "hard_brakes": hard_brakes,
                "jerks": jerks_step
            })

    return results



def compute_phased_stability(results, phase_windows):
    # Initialize accumulators
    phases = [
        PhaseAccumulator(phase_name, window[0], window[1])
        for phase_name, window in phase_windows.items()
    ]

    min_time = min(w[0] for w in phase_windows.values())
    max_time = max(w[1] for w in phase_windows.values())

    # Process each result
    for result in results:
        step_time = result["time"]
        if step_time < min_time or step_time > max_time:
            continue

        # Dispatch step values to the matching phase
        for phase in phases:
            if phase.contains(step_time):
                phase.add_step(result["speeds"], result["accelerations"], result["jerks"], result["hard_brakes"])
                break

    # Consolidate results per phase
    return {phase.name: phase.compute_summary() for phase in phases}


def summarize_stability_metrics_by_steps(results):
    summary = []
    for result in results:
        step_time = result["time"]
        speeds = result["speeds"]
        accelerations = result["accelerations"]
        hard_brakes = result["hard_brakes"]
        jerks_step = result["jerks"]

        mean_speed = float(np.mean(speeds)) if speeds else 0.0
        speed_std = float(np.std(speeds)) if speeds else 0.0
        accel_var = float(np.var(accelerations)) if accelerations else 0.0
        mean_abs_jerk = float(np.mean(np.abs(jerks_step))) if jerks_step else 0.0
        max_abs_jerk = float(np.max(np.abs(jerks_step))) if jerks_step else 0.0

        summary.append({
            "time": step_time,
            "mean_speed_mps": round(mean_speed, 4),
            "speed_std_mps": round(speed_std, 4),
            "accel_var_mps2": round(accel_var, 4),
            "hard_brake_events": hard_brakes,
            "mean_abs_jerk_mps3": round(mean_abs_jerk, 4),
            "max_abs_jerk_mps3": round(max_abs_jerk, 4)
        })

    return summary


def parse_and_compute_phased_stability(xml_file_path, phase_windows, exclude_ids):
    if not os.path.exists(xml_file_path):
        raise FileNotFoundError(f"File not found: {xml_file_path}")

    results = compute_steps_stability(xml_file_path, exclude_ids)

    step_summary = summarize_stability_metrics_by_steps(results)
    phased_results = compute_phased_stability(results, phase_windows)
    return step_summary, phased_results
