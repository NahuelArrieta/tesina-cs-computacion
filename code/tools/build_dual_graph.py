import os
import argparse
import xml.etree.ElementTree as ET
import math
import networkx as nx
import sumolib

def build_topological_skeleton(net_xml_path: str, effective_veh_length_m: float = 7.5) -> nx.DiGraph:
    """
    Parses the SUMO network using sumolib and constructs the dual graph topology.
    Nodes represent physical street segments (edges), and directed edges represent
    physically enabled maneuvers between adjacent segments.
    """
    if not os.path.exists(net_xml_path):
        raise FileNotFoundError(f"Network file not found: {net_xml_path}")

    net = sumolib.net.readNet(net_xml_path, withInternal=False)
    graph = nx.DiGraph()

    # Add nodes (SUMO edges)
    for edge in net.getEdges(withInternal=False):
        edge_id = edge.getID()
        length = float(edge.getLength())
        speed_limit = float(edge.getSpeed())
        num_lanes = int(edge.getLaneNumber())

        dx, dy = get_edge_direction(edge)

        capacity = num_lanes * math.floor(length / effective_veh_length_m)

        shape = edge.getShape()  # [(x1, y1), (x2, y2)]
        x_mid = (shape[0][0] + shape[-1][0]) / 2.0
        y_mid = (shape[0][1] + shape[-1][1]) / 2.0

        x_pos = float(round(x_mid, 2) * 2 + dx * 10)  # Adjust x based on direction
        y_pos = float(round(y_mid, 2) * 2 + dy * 10)  # Adjust y based on direction

        print(f"[INFO] Adding node: {edge_id}, x={x_pos}, y={y_pos}, dx={dx}, dy={dy}, x_mid={x_mid}, y_mid={y_mid}, length={length}")

        graph.add_node(
            edge_id,
            length_m=round(length, 2),
            speed_limit_mps=round(speed_limit, 2),
            num_lanes=num_lanes,
            capacity_veh=int(capacity),
            x=x_pos,
            y=y_pos
        )

    # Add edges (allowed maneuvers between edges)
    for edge in net.getEdges(withInternal=False):
        u = edge.getID()

        for target_edge, connections in edge.getOutgoing().items():
            v = target_edge.getID()

            if not graph.has_node(v):
                print(f"[WARN] Skipping connection from {u} to {v}: {v} edge is not in the graph.")
                continue

            if v.startswith(":"):
                continue # Ignore internal transition edges

            if graph.has_edge(u, v):
                continue  # Avoid duplicate edges

            conn = connections[0]
            graph.add_edge(
                u, 
                v, 
                raw_count=0, 
                weight=0.0,
                direction=str(conn.getDirection())
            )

    return graph


def compute_turning_counts(routes_xml_path: str) -> dict:
    """
    Parses routes.rou.xml using iterparse to count vehicular transitions
    between consecutive edges across all planned trips.
    """
    if not os.path.exists(routes_xml_path):
        raise FileNotFoundError(f"Routes file not found: {routes_xml_path}")

    transition_counts = {}
    context = ET.iterparse(routes_xml_path, events=("end",))

    for event, elem in context:
        edges_str = None
        if elem.tag == "vehicle":
            route_elem = elem.find("route")
            if route_elem is not None:
                edges_str = route_elem.get("edges")
        elif elem.tag == "route":
            edges_str = elem.get("edges")

        if edges_str:
            route_edges = edges_str.strip().split()
            for i in range(len(route_edges) - 1):
                u, v = route_edges[i], route_edges[i + 1]
                pair = (u, v)
                transition_counts[pair] = transition_counts.get(pair, 0) + 1

        elem.clear()

    del context
    return transition_counts

def get_edge_direction(edge: sumolib.net.edge) -> tuple[int, int]:
    """
    Returns the direction vector (dx, dy) of a SUMO edge based on its shape.
    """
    shape = edge.getShape()
    if len(shape) < 2:
        return (0, 0)
    x1, y1 = shape[0]
    x2, y2 = shape[-1]


    dx = 1 if x2 > x1 else -1 if x2 < x1 else 0
    dy = 1 if y2 > y1 else -1 if y2 < y1 else 0
    
    return (dx, dy)


def assign_turning_probabilities(graph: nx.DiGraph, turning_counts: dict) -> nx.DiGraph:
    """
    Assigns static turning ratios (beta_ij) as edge weights by normalizing
    observed vehicular transition counts per origin node.
    """
    # Inject raw transition counts into existing topological edges
    for (u, v), count in turning_counts.items():
        if graph.has_edge(u, v):
            graph[u][v]["raw_count"] = int(count)

    # Normalize probabilities per origin node
    for u in graph.nodes():
        successors = list(graph.successors(u))
        if not successors:
            continue

        total_outflow = sum(graph[u][v]["raw_count"] for v in successors)

        if total_outflow > 0:
            for v in successors:
                prob = graph[u][v]["raw_count"] / float(total_outflow)
                graph[u][v]["weight"] = round(prob, 4)
        else:
            # Fallback: uniform distribution if no demand passed through this segment
            uniform_prob = round(1.0 / len(successors), 4)
            for v in successors:
                graph[u][v]["weight"] = uniform_prob

    return graph


def export_dual_graph(graph: nx.DiGraph, output_graphml_path: str) -> None:
    """
    Exports the NetworkX DiGraph to a standard GraphML file.
    """
    out_dir = os.path.dirname(output_graphml_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    nx.write_graphml(graph, output_graphml_path)
    print(f"[OK] Dual graph successfully exported to: {output_graphml_path}")


def load_dual_graph(graphml_path: str) -> nx.DiGraph:
    """
    Loads and parses the dual graph from a GraphML file, casting attributes
    to their appropriate primitive types for downstream MPC/control consumption.
    """
    if not os.path.exists(graphml_path):
        raise FileNotFoundError(f"GraphML file not found: {graphml_path}")

    raw_graph = nx.read_graphml(graphml_path)
    graph = nx.DiGraph()

    # Reconstruct nodes with typed attributes
    for node, attrs in raw_graph.nodes(data=True):
        graph.add_node(
            node,
            length_m=float(attrs.get("length_m", 0.0)),
            speed_limit_mps=float(attrs.get("speed_limit_mps", 0.0)),
            num_lanes=int(attrs.get("num_lanes", 1)),
            capacity_veh=int(attrs.get("capacity_veh", 0))
        )

    # Reconstruct edges with typed attributes
    for u, v, attrs in raw_graph.edges(data=True):
        graph.add_edge(
            u,
            v,
            weight=float(attrs.get("weight", 0.0)),
            raw_count=int(attrs.get("raw_count", 0)),
            direction=str(attrs.get("direction", "s"))
        )

    return graph


def validate_graph(graph: nx.DiGraph) -> bool:
    """
    Runs basic topological checks to verify that edge turning probabilities
    sum to 1.0 (within precision limits) on all branching nodes.
    """
    errors = 0
    for u in graph.nodes():
        successors = list(graph.successors(u))
        if successors:
            total_weight = sum(graph[u][v]["weight"] for v in successors)
            if not math.isclose(total_weight, 1.0, abs_tol=1e-3):
                print(f"[WARN] Node {u} turning probabilities sum to {total_weight} != 1.0")
                errors += 1

    return errors == 0


def main():
    parser = argparse.ArgumentParser(description="Offline dual graph builder from SUMO network and routes.")
    parser.add_argument("--net", required=True, help="Path to grid.net.xml")
    parser.add_argument("--routes", required=True, help="Path to routes.rou.xml")
    parser.add_argument("--output", default="data/dual_graph.graphml", help="Path to output GraphML file")
    args = parser.parse_args()

    print("--- Building Dual Graph Topology ---")
    g = build_topological_skeleton(args.net)
    print(f"Topological base built: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges.")

    print("--- Extracting Turning Counts from Demand ---")
    counts = compute_turning_counts(args.routes)
    print(f"Distinct maneuvers with observed demand: {len(counts)}")

    print("--- Assigning Static Turning Ratios (Weights) ---")
    g = assign_turning_probabilities(g, counts)
    if not validate_graph(g):
        print("[ERROR] Graph validation failed: some nodes have turning probabilities that do not sum to 1.0")
        exit(1)

    print("--- Exporting GraphML ---")
    export_dual_graph(g, args.output)


if __name__ == "__main__":
    main()