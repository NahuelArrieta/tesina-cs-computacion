"""Generate CAV/HDV vehicle assignments for shared SUMO routes."""

from __future__ import annotations

import copy
import random
import xml.etree.ElementTree as ET
from pathlib import Path


def _load_human_distributions(vtypes_file: Path) -> list[ET.Element]:
    vtypes_root = ET.parse(vtypes_file).getroot()
    distributions = vtypes_root.findall("vTypeDistribution")
    if not distributions:
        raise ValueError(f"VTypes file contains no distributions: {vtypes_file}")
    if any(not distribution.get("id") for distribution in distributions):
        raise ValueError(f"VTypes distributions have no id: {vtypes_file}")
    return distributions


def _create_cav_type() -> ET.Element:
    return ET.Element(
        "vType",
        {
            "id": "CAV",
            "vClass": "passenger",
            "carFollowModel": "IDM",
            "accel": "2.6",
            "decel": "2.0",
            "emergencyDecel": "4.5",
            "tau": "0.5",
            "minGap": "2.0",
            "stepping": "0.1",
        },
    )


def assign_vehicle_types(
    route_file: Path,
    penetration: float,
    seed: int,
    vtypes_file: Path,
    vehicle_specs: list[dict[str, str]],
) -> int:
    """Write one penetration file with CAV and human vehicle assignments."""
    if not 0.0 <= penetration <= 1.0:
        raise ValueError("penetration must be between 0.0 and 1.0")

    distributions = _load_human_distributions(vtypes_file)
    vehicle_ids = [spec["id"] for spec in vehicle_specs]
    cav_count = round(len(vehicle_ids) * penetration)
    selected_cav_ids = set(
        random.Random(seed).sample(sorted(vehicle_ids), cav_count)
    )
    distribution_ids = [
        distribution_id
        for distribution in distributions
        if (distribution_id := distribution.get("id"))
    ]
    human_rng = random.Random(seed)

    root = ET.Element(
        "routes",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation":
                "http://sumo.dlr.de/xsd/routes_file.xsd",
        },
    )
    root.append(
        ET.Comment(
            f"cav_penetration={penetration:g}; routes_seed={seed}"
        )
    )
    root.insert(1, _create_cav_type())
    insert_at = 2
    for distribution in distributions:
        root.insert(insert_at, copy.deepcopy(distribution))
        insert_at += 1

    for spec in vehicle_specs:
        vehicle_type = (
            "CAV"
            if spec["id"] in selected_cav_ids
            else human_rng.choice(distribution_ids)
        )
        ET.SubElement(
            root,
            "vehicle",
            {
                "id": spec["id"],
                "depart": spec["depart"],
                "departLane": spec["departLane"],
                "departSpeed": spec["departSpeed"],
                "route": spec["route"],
                "type": vehicle_type,
            },
        )

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(route_file, encoding="utf-8", xml_declaration=True)
    return len(selected_cav_ids)
