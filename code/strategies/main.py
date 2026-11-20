from typing import Dict, Any
import traci


class Strategy:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def execute(self):
        raise NotImplementedError("Subclasses must implement the execute method.")


class DummyHoldStrategy(Strategy):
    """
    Prototype strategy that intermittently stops HDVs to induce
    controlled metric variations across scenarios (m0 -> m4).
    """

    def __init__(self, config: Dict[str, Any], hold_steps: int, cycle_steps: int = 100):
        super().__init__(config)
        self.hold_steps = hold_steps
        self.cycle_steps = cycle_steps
        self.step_count = 0
        self.held_vehicles = set()

    def execute(self):
        is_hold_phase = (self.step_count % self.cycle_steps) < self.hold_steps
        active_vehicles = traci.vehicle.getIDList()

        if is_hold_phase:
            for veh_id in active_vehicles:
                # Matches all profiles in the vTypeDistribution (e.g., hdv_car_0, hdv_car_1...)
                if traci.vehicle.getTypeID(veh_id).startswith("hdv"):
                    traci.vehicle.setSpeed(veh_id, 0.0)
                    self.held_vehicles.add(veh_id)
        elif self.held_vehicles:
            # Release only vehicles that are still in the simulation
            active_set = set(active_vehicles)
            for veh_id in self.held_vehicles:
                if veh_id in active_set:
                    traci.vehicle.setSpeed(veh_id, -1)
            self.held_vehicles.clear()

        self.step_count += 1


# Steps to hold HDVs out of every 100 simulation steps
DUMMY_PROFILES = {
    "m0": 40,  # Heavy congestion
    "m1": 30,
    "m2": 20,
    "m3": 10,
    "m4": 2,   # Minimal impact
}


def get_strategy(strategy_name: str, config: Dict[str, Any]) -> Strategy:
    name = strategy_name.lower()
    if name not in DUMMY_PROFILES:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    return DummyHoldStrategy(config, hold_steps=DUMMY_PROFILES[name])