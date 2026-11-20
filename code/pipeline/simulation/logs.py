import traci

def log(message):
    current_time = traci.simulation.getTime()
    print(f"[{current_time:.1f}s] {message}")