"""SUMO-GUI overlay for live subgraph occupancy and incident location."""

from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
import traci


VEHICLE_COUNT = traci.constants.LAST_STEP_VEHICLE_NUMBER
OVERLAY_LAYER = 100
INCIDENT_LAYER = OVERLAY_LAYER + 1


@dataclass(frozen=True)
class EdgeMeasurement:
    """Vehicle count and normalized occupancy for one SUMO edge."""

    vehicle_count: int
    occupancy: float


class SubgraphMonitor:
    """Collect subgraph edge counts using TraCI subscriptions."""

    def __init__(self, subgraph: nx.DiGraph) -> None:
        self._capacities = {
            edge_id: int(attributes.get("capacity_veh", 0))
            for edge_id, attributes in subgraph.nodes(data=True)
        }
        available_edges = set(traci.edge.getIDList())
        self._edge_ids = [
            edge_id
            for edge_id in subgraph.nodes
            if edge_id in available_edges
        ]
        for edge_id in self._edge_ids:
            traci.edge.subscribe(edge_id, (VEHICLE_COUNT,))

    def sample(self) -> dict[str, EdgeMeasurement]:
        """Return the latest count and occupancy for every subgraph edge."""
        measurements = {}
        for edge_id, capacity in self._capacities.items():
            result = traci.edge.getSubscriptionResults(edge_id) or {}
            vehicle_count = int(result.get(VEHICLE_COUNT, 0))
            occupancy = (
                max(0.0, min(1.0, vehicle_count / capacity))
                if capacity > 0
                else 0.0
            )
            measurements[edge_id] = EdgeMeasurement(vehicle_count, occupancy)
        return measurements


class SumoGuiOverlay:
    """Display occupancy and incident markers directly in SUMO-GUI."""

    def __init__(
        self,
        subgraph: nx.DiGraph,
        incident_edge: str,
        show_occupancy: bool,
    ) -> None:
        self._polygon_ids = {
            edge_id: f"subgraph-occupancy-{edge_id}"
            for edge_id in subgraph.nodes
        }
        self._active_polygon_ids: set[str] = set()
        self._closed = False
        lane_shapes = self._load_lane_shapes(subgraph.nodes)

        if show_occupancy:
            for edge_id, shape in lane_shapes.items():
                self._add_occupancy_overlay(
                    edge_id,
                    shape,
                    subgraph,
                )

        incident_shape = lane_shapes.get(incident_edge)
        if incident_shape:
            self._add_incident_marker(incident_shape)

    def update(self, measurements: dict[str, EdgeMeasurement]) -> None:
        """Update occupancy colors in SUMO-GUI."""
        for edge_id, measurement in measurements.items():
            polygon_id = self._polygon_ids[edge_id]
            if polygon_id not in self._active_polygon_ids:
                continue
            red = int(255 * measurement.occupancy)
            green = int(255 * (1.0 - measurement.occupancy))
            traci.polygon.setColor(polygon_id, (red, green, 0, 180))

    def close(self) -> None:
        """Remove all custom polygons from SUMO-GUI."""
        if self._closed:
            return
        for polygon_id in self._active_polygon_ids:
            traci.polygon.remove(polygon_id, layer=OVERLAY_LAYER)
            traci.polygon.remove(polygon_id, layer=INCIDENT_LAYER)
        self._closed = True

    def _add_occupancy_overlay(
        self,
        edge_id: str,
        shape: list[tuple[float, float]],
        subgraph: nx.DiGraph,
    ) -> None:
        turn_ratio = max(
            (
                float(attributes.get("weight", 0.0))
                for _, _, attributes in subgraph.out_edges(edge_id, data=True)
            ),
            default=0.0,
        )
        polygon_id = self._polygon_ids[edge_id]
        traci.polygon.add(
            polygon_id,
            shape,
            (0, 180, 0, 180),
            fill=False,
            layer=OVERLAY_LAYER,
            lineWidth=2.0 + 8.0 * turn_ratio,
        )
        self._active_polygon_ids.add(polygon_id)

    def _add_incident_marker(self, shape: list[tuple[float, float]]) -> None:
        center = _polyline_midpoint(shape)
        marker = [
            (
                center[0] + 15.0 * math.cos(angle),
                center[1] + 15.0 * math.sin(angle),
            )
            for angle in (index * math.pi / 12 for index in range(24))
        ]
        polygon_id = "subgraph-incident-marker"
        traci.polygon.add(
            polygon_id,
            marker,
            (220, 0, 0, 220),
            fill=True,
            layer=INCIDENT_LAYER,
            lineWidth=3.0,
        )
        self._active_polygon_ids.add(polygon_id)

    @staticmethod
    def _load_lane_shapes(
        edge_ids: object,
    ) -> dict[str, list[tuple[float, float]]]:
        lane_ids_by_edge: dict[str, list[str]] = {}
        for lane_id in traci.lane.getIDList():
            edge_id = traci.lane.getEdgeID(lane_id)
            lane_ids_by_edge.setdefault(edge_id, []).append(lane_id)

        shapes = {}
        for edge_id in edge_ids:
            lane_ids = lane_ids_by_edge.get(edge_id, [])
            if lane_ids:
                shapes[edge_id] = [
                    (float(x), float(y))
                    for x, y in traci.lane.getShape(lane_ids[0])
                ]
        return shapes


def _polyline_midpoint(
    shape: list[tuple[float, float]],
) -> tuple[float, float]:
    """Return the point halfway along a polyline."""
    if len(shape) < 2:
        return shape[0] if shape else (0.0, 0.0)

    segment_lengths = [
        math.hypot(
            shape[index + 1][0] - shape[index][0],
            shape[index + 1][1] - shape[index][1],
        )
        for index in range(len(shape) - 1)
    ]
    target = sum(segment_lengths) / 2.0
    distance = 0.0
    for index, segment_length in enumerate(segment_lengths):
        if distance + segment_length >= target:
            ratio = (
                (target - distance) / segment_length
                if segment_length > 0.0
                else 0.0
            )
            start, end = shape[index], shape[index + 1]
            return (
                start[0] + ratio * (end[0] - start[0]),
                start[1] + ratio * (end[1] - start[1]),
            )
        distance += segment_length
    return shape[-1]
