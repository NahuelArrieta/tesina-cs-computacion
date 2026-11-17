"""Live visualization of a dual-graph subgraph using TraCI measurements."""

from __future__ import annotations

import importlib

import matplotlib


def _configure_interactive_backend() -> None:
    """Select a GUI backend before importing pyplot."""
    try:
        importlib.import_module("tkinter")
    except ImportError as error:
        raise RuntimeError(
            "Live visualization needs tkinter. Install it with "
            "'sudo apt install python3-tk', then rerun the simulation."
        ) from error
    matplotlib.use("TkAgg", force=True)


_configure_interactive_backend()
import matplotlib.pyplot as plt
import networkx as nx
import traci
from matplotlib.colors import Normalize


class SubgraphVisualizer:
    """Render a dual graph with live congestion and turning probabilities."""

    def __init__(self, subgraph: nx.DiGraph) -> None:
        self.subgraph = subgraph
        self._edge_ids = set(traci.edge.getIDList())
        self._positions = {
            node: (float(data.get("x", 0.0)), float(data.get("y", 0.0)))
            for node, data in subgraph.nodes(data=True)
        }
        self._figure, self._axis = plt.subplots(figsize=(12, 9))
        self._figure.canvas.manager.set_window_title("SUMO subgraph monitor")
        self._figure.show()
        self._configure_overlay_window()
        self._draw_static_graph()

    def update(self, time_s: float) -> None:
        """Sample TraCI and refresh the lightweight live visualization."""
        congestion: dict[str, float] = {}
        for node, attributes in self.subgraph.nodes(data=True):
            if node not in self._edge_ids:
                vehicle_count = 0
                node_congestion = 0.0
            else:
                vehicle_count = int(traci.edge.getLastStepVehicleNumber(node))
                capacity = int(attributes.get("capacity_veh", 0))
                node_congestion = (
                    max(0.0, min(1.0, vehicle_count / capacity))
                    if capacity > 0
                    else 0.0
                )
            congestion[node] = node_congestion

        node_values = [congestion[node] for node in self.subgraph.nodes]
        self._nodes.set_array(node_values)
        self._axis.set_title(
            f"Subgraph at t={time_s:.1f}s "
            "(node color = vehicles / capacity; edge width = turn ratio)"
        )
        self._figure.canvas.draw_idle()
        self._figure.canvas.flush_events()

    def close(self) -> None:
        """Close the live visualization window."""
        plt.close(self._figure)

    def _configure_overlay_window(self) -> None:
        """Keep the monitor above SUMO without repeatedly taking focus."""
        window = self._figure.canvas.manager.window
        window.wm_attributes("-topmost", True)
        window.attributes("-topmost", True)
        window.focusmodel("passive")

    def _draw_static_graph(self) -> None:
        """Draw graph topology and return reusable node artists."""
        nx.draw_networkx_edges(
            self.subgraph,
            self._positions,
            ax=self._axis,
            width=[
                1.0 + 8.0 * float(attributes.get("weight", 0.0))
                for _, _, attributes in self.subgraph.edges(data=True)
            ],
            edge_color="#555555",
            arrows=True,
            arrowsize=16,
            connectionstyle="arc3,rad=0.04",
        )
        self._nodes = nx.draw_networkx_nodes(
            self.subgraph,
            self._positions,
            ax=self._axis,
            node_color=[0.0] * self.subgraph.number_of_nodes(),
            cmap="RdYlGn_r",
            vmin=0.0,
            vmax=1.0,
            node_size=700,
            edgecolors="black",
            linewidths=0.8,
        )
        nx.draw_networkx_labels(
            self.subgraph,
            self._positions,
            ax=self._axis,
            font_size=7,
            font_color="black",
        )
        colorbar = self._figure.colorbar(
            plt.cm.ScalarMappable(norm=Normalize(0.0, 1.0), cmap="RdYlGn_r"),
            ax=self._axis,
            label="Occupancy (vehicles / edge capacity)",
        )
        colorbar.set_ticks([0.0, 0.5, 1.0])
        self._axis.set_axis_off()
        self._figure.tight_layout()
