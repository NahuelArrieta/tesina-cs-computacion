"""Write SUMO configuration files for Stage 2 experiments."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def write_sumo_config(
    output_file: Path,
    network_file: Path,
    routes_file: Path,
    detectors_file: Path,
    simulation: dict[str, Any],
) -> None:
    """Write a SUMO configuration referencing an experiment's artifacts."""
    root = ET.Element("configuration")
    input_node = ET.SubElement(root, "input")
    ET.SubElement(input_node, "net-file", {"value": str(network_file)})
    ET.SubElement(input_node, "route-files", {"value": str(routes_file)})
    ET.SubElement(input_node, "additional-files", {"value": str(detectors_file)})
    time_node = ET.SubElement(root, "time")
    for key, config_key in (
        ("begin", "begin_s"),
        ("end", "end_s"),
        ("step-length", "step_length_s"),
    ):
        ET.SubElement(time_node, key, {"value": str(simulation[config_key])})
    ET.indent(root, space="    ")
    output_file.write_text(
        ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8"
    )
