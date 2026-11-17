"""Interactive monitoring of a dual-graph subgraph during a TraCI simulation."""

from __future__ import annotations

import importlib
import math
import time
from dataclasses import dataclass
from typing import Mapping

import matplotlib


def _configure_interactive_backend() -> None:
    """Select a GUI backend before importing pyplot."""
    try:
        importlib.import_module("tkinter")
    except ImportError as error:
        raise RuntimeError(
            "Live visualization needs tkinter. Install it with "
            "'sudo apt install python3-tk'."
        ) from error
    matplotlib.use("TkAgg", force=True)


import networkx as nx
import traci


@dataclass(frozen=True)
class EdgeMeasurement:
    """Live occupancy measurement for one SUMO edge."""

    vehicle_count: int
    occupancy: float


class SubgraphMonitor:
    """Collect edge vehicle counts through TraCI subscriptions."""

    def __init__(self, subgraph: nx.DiGraph) -> None:
        self._subgraph = subgraph
        self._capacities = {
            node: int(data.get("capacity_veh", 0))
            for node, data in subgraph.nodes(data=True)
        }
        edge_ids = set(traci.edge.getIDList())
        self._edge_ids = [
            node for node in subgraph.nodes if node in edge_ids
        ]
        for edge_id in self._edge_ids:
            traci.edge.subscribe(
                edge_id,
                (traci.constants.LAST_STEP_VEHICLE_NUMBER,),
            )

    def sample(self) -> dict[str, EdgeMeasurement]:
        """Return the latest vehicle counts and normalized occupancies."""
        measurements: dict[str, EdgeMeasurement] = {}
        for node in self._subgraph.nodes:
            results = traci.edge.getSubscriptionResults(node)
            vehicle_count = int(
                results.get(traci.constants.LAST_STEP_VEHICLE_NUMBER, 0)
                if results
                else 0
            )
            capacity = self._capacities[node]
            occupancy = (
                max(0.0, min(1.0, vehicle_count / capacity))
                if capacity > 0
                else 0.0
            )
            measurements[node] = EdgeMeasurement(vehicle_count, occupancy)
        return measurements


class SumoGuiRenderer:
    """Color the real SUMO-GUI streets with transparent polygon overlays."""

    def __init__(self, subgraph: nx.DiGraph, incident_edge: str, show_overlay: bool) -> None:
        self._polygon_ids = {
            node: f"subgraph-monitor-{node}" for node in subgraph.nodes
        }
        self._active_polygon_ids: set[str] = set()
        self._incident_polygon_id = "subgraph-monitor-incident"
        self._closed = False
        for node in subgraph.nodes:
            if not show_overlay:
                break
            shape = self._get_edge_shape(node)
            if shape:
                polygon_id = self._polygon_ids[node]
                traci.polygon.add(
                    polygon_id,
                    shape,
                    (0, 180, 0, 180),
                    fill=False,
                    layer=100,
                    lineWidth=max(
                        2.0,
                        2.0
                        + 8.0
                        * max(
                            (
                                float(data.get("weight", 0.0))
                                for _, _, data in subgraph.out_edges(node, data=True)
                            ),
                            default=0.0,
                        ),
                    ),
                )
                self._active_polygon_ids.add(polygon_id)
        incident_shape = self._get_edge_shape(incident_edge)
        if incident_shape:
            midpoint = self._polyline_midpoint(incident_shape)
            marker_shape = [
                (
                    midpoint[0] + 15.0 * math.cos(angle),
                    midpoint[1] + 15.0 * math.sin(angle),
                )
                for angle in [i * math.pi / 12 for i in range(24)]
            ]
            traci.polygon.add(
                self._incident_polygon_id,
                marker_shape,
                (220, 0, 0, 220),
                fill=True,
                layer=101,
                lineWidth=3.0,
            )
            self._active_polygon_ids.add(self._incident_polygon_id)

    def update(
        self, time_s: float, measurements: Mapping[str, EdgeMeasurement]
    ) -> None:
        """Update SUMO-GUI overlay colors."""
        for node, measurement in measurements.items():
            polygon_id = self._polygon_ids[node]
            if polygon_id not in self._active_polygon_ids:
                continue
            occupancy = measurement.occupancy
            red = int(255 * occupancy)
            green = int(255 * (1.0 - occupancy))
            traci.polygon.setColor(
                polygon_id, (red, green, 0, 180)
            )

    def is_open(self) -> bool:
        return not self._closed

    def process_events(self) -> None:
        return

    def close(self) -> None:
        if not self._closed:
            for polygon_id in self._active_polygon_ids:
                traci.polygon.remove(polygon_id, layer=100)
            self._closed = True

    @staticmethod
    def _get_edge_shape(edge_id: str) -> list[tuple[float, float]]:
        """Return the geometry of the first lane belonging to an edge."""
        lane_ids = [
            lane_id
            for lane_id in traci.lane.getIDList()
            if traci.lane.getEdgeID(lane_id) == edge_id
        ]
        if not lane_ids:
            return []
        return [
            (float(x), float(y))
            for x, y in traci.lane.getShape(lane_ids[0])
        ]

    @staticmethod
    def _polyline_midpoint(
        shape: list[tuple[float, float]],
    ) -> tuple[float, float]:
        """Return the point halfway along a lane polyline."""
        lengths = [
            math.hypot(
                shape[index + 1][0] - shape[index][0],
                shape[index + 1][1] - shape[index][1],
            )
            for index in range(len(shape) - 1)
        ]
        half_length = sum(lengths) / 2.0
        distance = 0.0
        for index, segment_length in enumerate(lengths):
            if distance + segment_length >= half_length:
                ratio = (
                    (half_length - distance) / segment_length
                    if segment_length > 0.0
                    else 0.0
                )
                start = shape[index]
                end = shape[index + 1]
                return (
                    start[0] + ratio * (end[0] - start[0]),
                    start[1] + ratio * (end[1] - start[1]),
                )
            distance += segment_length
        return shape[len(shape) // 2]


class SubgraphRenderer:
    """Render fixed graph topology and update only live node colors."""

    def __init__(self, subgraph: nx.DiGraph, incident_edge: str) -> None:
        _configure_interactive_backend()
        import matplotlib.pyplot as plt
        from matplotlib.colors import Normalize

        self._subgraph = subgraph
        self._plt = plt
        self._normalize = Normalize
        self._title = None
        self._incident_edge = incident_edge
        self._positions = {
            node: (float(data.get("x", 0.0)), float(data.get("y", 0.0)))
            for node, data in subgraph.nodes(data=True)
        }
        self.figure, self.axis = self._plt.subplots(figsize=(12, 9))
        self.figure.canvas.manager.set_window_title("SUMO subgraph monitor")
        self.figure.show()
        self._configure_overlay_window()
        self._draw_static_graph()

    def update(
        self, time_s: float, measurements: Mapping[str, EdgeMeasurement]
    ) -> None:
        """Update node colors and title without rebuilding the graph."""
        self._nodes.set_array(
            [measurements[node].occupancy for node in self._subgraph.nodes]
        )
        self._title.set_text(
            f"Subgraph at t={time_s:.1f}s "
            "(node color = vehicles / capacity; edge width = turn ratio)"
        )
        self.figure.canvas.draw_idle()

    def is_open(self) -> bool:
        """Return whether the monitor window still exists."""
        return self._plt.fignum_exists(self.figure.number)

    def process_events(self) -> None:
        """Process GUI events without deliberately taking focus."""
        self.figure.canvas.flush_events()
        self.figure.canvas.manager.window.update_idletasks()
        self.figure.canvas.manager.window.update()

    def close(self) -> None:
        """Close the live visualization window."""
        self._plt.close(self.figure)

    def _configure_overlay_window(self) -> None:
        window = self.figure.canvas.manager.window
        window.wm_attributes("-topmost", True)
        window.attributes("-topmost", True)
        window.focusmodel("passive")

    def _draw_static_graph(self) -> None:
        nx.draw_networkx_edges(
            self._subgraph,
            self._positions,
            ax=self.axis,
            width=[
                1.0 + 8.0 * float(attributes.get("weight", 0.0))
                for _, _, attributes in self._subgraph.edges(data=True)
            ],
            edge_color="#555555",
            arrows=True,
            arrowsize=16,
            connectionstyle="arc3,rad=0.04",
        )
        self._nodes = nx.draw_networkx_nodes(
            self._subgraph,
            self._positions,
            ax=self.axis,
            node_color=[0.0] * self._subgraph.number_of_nodes(),
            cmap="RdYlGn_r",
            vmin=0.0,
            vmax=1.0,
            node_size=700,
            edgecolors="black",
            linewidths=0.8,
        )
        nx.draw_networkx_labels(
            self._subgraph,
            self._positions,
            ax=self.axis,
            font_size=7,
            font_color="black",
        )
        if incident_edge := self._positions.get(self._incident_edge):
            self.axis.scatter(
                [incident_edge[0]],
                [incident_edge[1]],
                s=1300,
                facecolors="none",
                edgecolors="#d00000",
                linewidths=3.0,
                zorder=5,
            )
        colorbar = self.figure.colorbar(
            self._plt.cm.ScalarMappable(
                norm=self._normalize(0.0, 1.0), cmap="RdYlGn_r"
            ),
            ax=self.axis,
            label="Occupancy (vehicles / edge capacity)",
        )
        colorbar.set_ticks([0.0, 0.5, 1.0])
        self.axis.set_axis_off()
        self._title = self.figure.suptitle(
            "Subgraph monitor",
            y=0.98,
            fontsize=12,
        )
        self.figure.subplots_adjust(top=0.90, bottom=0.04, left=0.02, right=0.93)


class PlaybackController:
    """Handle monitor controls and pace SUMO without owning TraCI."""

    def __init__(
        self,
        renderer: SubgraphRenderer | SumoGuiRenderer,
        step_length_s: float,
        interactive_controls: bool,
    ) -> None:
        if step_length_s <= 0.0:
            raise ValueError("step_length_s must be positive")
        self._renderer = renderer
        self._step_length_s = step_length_s
        self._paused = False
        self._playback_speed = 1.0
        self._last_step_wall_time = time.monotonic()
        self._interactive_controls = interactive_controls
        if interactive_controls:
            self._configure_controls()

    def wait_for_next_step(self) -> bool:
        """Process controls and wait until the next SUMO step may run."""
        if not self._interactive_controls:
            return True
        self._process_events()
        while self._paused and self._renderer.is_open():
            time.sleep(0.05)
            self._process_events()
        if not self._renderer.is_open():
            return False
        target_interval = self._step_length_s / self._playback_speed
        elapsed = time.monotonic() - self._last_step_wall_time
        if elapsed < target_interval:
            time.sleep(target_interval - elapsed)
            self._process_events()
        self._last_step_wall_time = time.monotonic()
        return self._renderer.is_open()

    def _process_events(self) -> None:
        self._renderer.process_events()

    def _configure_controls(self) -> None:
        import tkinter as tk

        window = self._renderer.figure.canvas.manager.window
        controls = tk.Frame(window)
        controls.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Button(
            controls, text="Pause / resume", command=self._toggle_pause
        ).pack(side=tk.LEFT)
        tk.Button(
            controls, text="Slower (-)", command=lambda: self._change_speed(0.5)
        ).pack(side=tk.LEFT)
        tk.Button(
            controls, text="Faster (+)", command=lambda: self._change_speed(2.0)
        ).pack(side=tk.LEFT)
        window.bind("<space>", lambda _event: self._toggle_pause())
        window.bind("<plus>", lambda _event: self._change_speed(2.0))
        window.bind("<equal>", lambda _event: self._change_speed(2.0))
        window.bind("<minus>", lambda _event: self._change_speed(0.5))
        window.bind("<KP_Add>", lambda _event: self._change_speed(2.0))
        window.bind("<KP_Subtract>", lambda _event: self._change_speed(0.5))

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._update_status_title()

    def _change_speed(self, multiplier: float) -> None:
        self._playback_speed = max(0.125, min(8.0, self._playback_speed * multiplier))
        self._update_status_title()

    def _update_status_title(self) -> None:
        state = "PAUSED" if self._paused else "RUNNING"
        self._renderer.figure.canvas.manager.set_window_title(
            f"SUMO subgraph monitor - {state} - {self._playback_speed:g}x"
        )


class SubgraphVisualizer:
    """Coordinate monitoring, rendering, and playback controls."""

    def __init__(
        self,
        subgraph: nx.DiGraph,
        step_length_s: float,
        incident_edge: str,
        sumo_gui: bool = False,
        show_overlay: bool = False,
    ) -> None:
        self._renderer = (
            SumoGuiRenderer(subgraph, incident_edge, show_overlay)
            if sumo_gui
            else SubgraphRenderer(subgraph, incident_edge)
        )
        self._monitor = SubgraphMonitor(subgraph) if show_overlay or not sumo_gui else None
        self._controller = PlaybackController(
            self._renderer,
            step_length_s,
            interactive_controls=not sumo_gui,
        )

    def update(self, time_s: float) -> None:
        """Sample TraCI and update the live graph."""
        measurements = self._monitor.sample() if self._monitor else {}
        self._renderer.update(time_s, measurements)

    def wait_for_next_step(self) -> bool:
        """Process controls and return whether the monitor remains open."""
        return self._controller.wait_for_next_step()

    def close(self) -> None:
        """Close the live visualization window."""
        self._renderer.close()
