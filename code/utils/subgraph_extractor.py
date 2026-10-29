#!/usr/bin/env python3
"""
subgraph_extractor.py

Extracts the upstream topological influence subgraph for a given incident edge
using backward search guided by accumulated turning probabilities (beta_ij).
Outputs both the list of controlled edge IDs and an induced GraphML file for yEd visualization.
"""

import argparse
import heapq
import math
import sys
from typing import Dict, List, Set, Tuple
import networkx as nx


class MaxPriorityQueue:
    """Heap-backed priority queue that exposes positive priorities."""

    def __init__(self) -> None:
        self._items: List[Tuple[float, int, str]] = []

    def put(self, probability: float, hops: int, node_id: str) -> None:
        """Add a node, keeping the highest probability at the front."""
        if not math.isfinite(probability) or probability < 0.0:
            raise ValueError(
                f"Probability must be finite and non-negative, got {probability}."
            )
        heapq.heappush(self._items, (-probability, hops, node_id))

    def get(self) -> Tuple[float, int, str]:
        """Remove and return the highest-probability node."""
        neg_probability, hops, node_id = heapq.heappop(self._items)
        return -neg_probability, hops, node_id

    def __bool__(self) -> bool:
        return bool(self._items)


def extract_upstream_subgraph(
    graph: nx.DiGraph,
    incident_edge: str,
    min_prob_threshold: float = 0.05,
    max_hops: int = 4
) -> nx.DiGraph:
    """
    Performs backward search upstream from incident_edge based on turning probabilities.

    Args:
        graph: Full dual directed graph where nodes are edges and edges are turns with 'weight'.
        incident_edge: Target edge ID where the incident occurs.
        min_prob_threshold: Cumulative turning probability threshold to prune branches.
        max_hops: Maximum number of backward intersections (hops) to traverse.

    Returns:
        induced_subgraph: NetworkX DiGraph containing the upstream basin.
    """
    if incident_edge not in graph:
        raise ValueError(f"Incident edge '{incident_edge}' not found in the provided graph.")

    priority_queue = MaxPriorityQueue()
    priority_queue.put(1.0, 0, incident_edge)
    
    # Track the highest accumulated probability reached for each node
    best_prob: Dict[str, float] = {incident_edge: 1.0}
    upstream_nodes: Set[str] = {incident_edge}

    while priority_queue:
        current_prob, hops, current_node = priority_queue.get()

        # Check max hops constraint
        if hops >= max_hops:
            continue

        for pred_node in graph.predecessors(current_node):
            edge_data = graph.get_edge_data(pred_node, current_node, default={})
            
            turn_prob = float(edge_data.get("weight", 0.0))

            # Calculate cumulative probability of reaching the bottleneck via this maneuver
            accumulated_prob = current_prob * turn_prob

            # Prune marginal influence paths
            if accumulated_prob < min_prob_threshold:
                continue

            # Relaxation step: update if a higher probability path is found
            if accumulated_prob > best_prob.get(pred_node, 0.0):
                best_prob[pred_node] = accumulated_prob
                upstream_nodes.add(pred_node)
                priority_queue.put(accumulated_prob, hops + 1, pred_node)

    subgraph = graph.subgraph(upstream_nodes).copy()

    for node in subgraph.nodes():
        subgraph.nodes[node]["upstream_prob"] = round(best_prob.get(node, 0.0), 4)

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