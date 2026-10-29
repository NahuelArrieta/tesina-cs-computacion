import traci
from .logs import log


class IncidentManager:
    def __init__(self, veh_id="veh_bloqueo", route_id="ruta_incidente"):
        self.veh_id = veh_id
        self.route_id = route_id
        self.is_active = False
        self.incident_edge = None
        self.blocked_lane_index = None

    def _log(self, message):
        log(message)

    def start(self, incident_edge, blocked_lane_index):
        if self.is_active:
            return False

        lane_id = f"{incident_edge}_{blocked_lane_index}"
        lane_length = traci.lane.getLength(lane_id)
        stop_pos = lane_length / 2.0

        if self.route_id not in traci.route.getIDList():
            traci.route.add(self.route_id, [incident_edge])

        traci.vehicle.add(
            vehID=self.veh_id,
            routeID=self.route_id,
            departLane=str(blocked_lane_index),
            departPos=str(max(0.0, stop_pos-10.0)),
            departSpeed="0"
        )

        traci.vehicle.setColor(self.veh_id, (255, 0, 0, 255))

        traci.vehicle.setStop(
            vehID=self.veh_id,
            edgeID=incident_edge,
            pos=stop_pos,
            laneIndex=blocked_lane_index,
            flags=0
        )

        self._log(f"Obstrucción activa en el carril: {lane_id}")
        self.is_active = True
        self.incident_edge = incident_edge
        self.blocked_lane_index = blocked_lane_index
        return True

    def end(self):
        if not self.is_active:
            return False

        lane_id = f"{self.incident_edge}_{self.blocked_lane_index}"

        if self.veh_id in traci.vehicle.getIDList():
            traci.vehicle.resume(self.veh_id)

        self.is_active = False
        self._log(f"Obstrucción finalizada. Carril despejado: {lane_id}")
        
        self.incident_edge = None
        self.blocked_lane_index = None
        return True