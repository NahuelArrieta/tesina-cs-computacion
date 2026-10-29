#!/usr/bin/env python3
"""
subgraph_extractor.py

Extracts the upstream topological influence subgraph for a given incident edge
using backward search guided by accumulated turning probabilities (beta_ij).
Outputs both the list of controlled edge IDs and an induced GraphML file for yEd visualization.
"""

import heapq
import math
from typing import Dict, List, Set, Tuple
import networkx as nx


class MaxPriorityQueue:
    """Heap-backed priority queue that exposes positive priorities."""

    def __init__(self) -> None:
        self._items: List[Tuple[float, float, str]] = []

    def put(self, probability: float, seconds_traveled: float, node_id: str) -> None:
        """Add a node, keeping the highest probability at the front."""
        if not math.isfinite(probability) or probability < 0.0:
            raise ValueError(
                f"Probability must be finite and non-negative, got {probability}."
            )
        heapq.heappush(self._items, (-probability, seconds_traveled, node_id))

    def get(self) -> Tuple[float, float, str]:
        """Remove and return the highest-probability node."""
        neg_probability, seconds_traveled, node_id = heapq.heappop(self._items)
        return -neg_probability, seconds_traveled, node_id

    def __bool__(self) -> bool:
        return bool(self._items)


def extract_upstream_subgraph(
    graph: nx.DiGraph,
    incident_edge: str,
    min_prob_threshold: float = 0.05,
    max_seconds_travel: float = 180.0,
    intersection_delay: float = 10.0,
) -> nx.DiGraph:
    """
    Performs backward search upstream from incident_edge based on turning probabilities
    and free-flow travel time constraints.
    """
    if incident_edge not in graph:
        raise ValueError(f"Incident edge '{incident_edge}' not found in the provided graph.")

    priority_queue = MaxPriorityQueue()
    priority_queue.put(1.0, 0.0, incident_edge)
    
    best_state: Dict[str, Tuple[float, float]] = {incident_edge: (1.0, 0.0)}

    while priority_queue:
        current_prob, current_time, current_node = priority_queue.get()

        # If a strictly better path to current_node was already processed, skip stale entry
        if current_prob < best_state[current_node][0]:
            continue

        for pred_node in graph.predecessors(current_node):
            edge_data = graph.get_edge_data(pred_node, current_node, default={})
            node_data = graph.nodes[pred_node]
            
            turn_prob = float(edge_data.get("weight", 0.0))
            accumulated_prob = current_prob * turn_prob

            # Prune by turning probability
            if accumulated_prob < min_prob_threshold:
                continue

            length_m = float(node_data.get("length_m", 0.0))
            speed_limit = float(node_data.get("speed_limit_mps", 13.89))
            seg_travel_time = length_m / speed_limit if speed_limit > 0 else 0.0
            
            new_travel_time = current_time + seg_travel_time + intersection_delay

            # Prune strictly by travel time horizon BEFORE including the node
            if new_travel_time > max_seconds_travel:
                continue

            # Relaxation step: update if we found a path with higher upstream probability
            prev_best_prob, _ = best_state.get(pred_node, (0.0, float("inf")))
            if accumulated_prob > prev_best_prob:
                best_state[pred_node] = (accumulated_prob, new_travel_time)
                priority_queue.put(accumulated_prob, new_travel_time, pred_node)

    # Induce subgraph strictly with valid reaching nodes
    upstream_nodes = set(best_state.keys())
    subgraph = graph.subgraph(upstream_nodes).copy()

    for node in subgraph.nodes():
        prob, travel_t = best_state[node]
        subgraph.nodes[node]["upstream_prob"] = round(prob, 4)
        subgraph.nodes[node]["travel_time_s"] = round(travel_t, 2)

    return subgraph


def get_alternative_routes(graph: nx.DiGraph, subgraph: nx.DiGraph) -> Set[str]:
    """
    Identifies alternative downstream routes branching off the upstream subgraph.

    Args:
        graph: Full dual directed graph.
        subgraph: Induced upstream subgraph containing controlled nodes

    Returns:
        alternative_routes: Set of downstream nodes (S_alt) that are not part of S_ctrl.
    """
    upstream_nodes = set(subgraph.nodes())

    alternative_routes: Set[str] = set()

    for node in upstream_nodes:
        for succ_node in graph.successors(node):
            if succ_node not in upstream_nodes:
                alternative_routes.add(succ_node)

    return alternative_routes