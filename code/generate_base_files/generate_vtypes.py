"""Generate the homogeneous human-driver vehicle type used by SUMO."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd


REQUIRED_COLUMNS = {"type", "Accel_Mean", "Decel_Mean", "Speed_Mean"}
VEHICLE_TYPE_PERCENTAGES = {"Car": 100.0}
CAR_FOLLOW_MODEL = "Krauss"
VEHICLE_LENGTH = "4.5"
MINIMUM_GAP = "2.5"
REACTION_TIME = "1.2"
KRAUSS_SIGMA = "0.5"


def generate_vtypes(input_file: Path, output_file: Path) -> None:
    """Create SUMO vehicle types from the configured rows in a parameter CSV."""
    if not math.isclose(sum(VEHICLE_TYPE_PERCENTAGES.values()), 100.0):
        raise ValueError("VEHICLE_TYPE_PERCENTAGES must sum to 100")
    if any(percentage <= 0 for percentage in VEHICLE_TYPE_PERCENTAGES.values()):
        raise ValueError("VEHICLE_TYPE_PERCENTAGES must contain positive values")

    parameters = pd.read_csv(input_file)
    missing_columns = REQUIRED_COLUMNS - set(parameters.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CSV is missing required columns: {missing}")

    root = ET.Element("additional")
    for vehicle_type in VEHICLE_TYPE_PERCENTAGES:
        type_parameters = parameters.loc[parameters["type"].eq(vehicle_type)]
        if len(type_parameters) != 1:
            raise ValueError(
                f"Expected exactly one row with type == '{vehicle_type}', "
                f"found {len(type_parameters)}"
            )

        row = type_parameters.iloc[0]
        try:
            attributes = {
                "id": f"hdv_{vehicle_type.lower()}",
                "carFollowModel": CAR_FOLLOW_MODEL,
                "accel": f"{float(row['Accel_Mean']):.2f}",
                "decel": f"{float(row['Decel_Mean']):.2f}",
                "maxSpeed": f"{float(row['Speed_Mean']):.2f}",
                "length": VEHICLE_LENGTH,
                "minGap": MINIMUM_GAP,
                "tau": REACTION_TIME,
                "sigma": KRAUSS_SIGMA,
            }
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{vehicle_type} row contains a non-numeric value in "
                "Accel_Mean, Decel_Mean, or Speed_Mean"
            ) from error
        ET.SubElement(root, "vType", attributes)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate SUMO human-driver vehicle types from a CSV."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("sumo_vtype_parameters.csv"),
        help="Input CSV file (default: sumo_vtype_parameters.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("vtypes.add.xml"),
        help="Output SUMO additional file (default: vtypes.add.xml)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_vtypes(args.input, args.output)


if __name__ == "__main__":
    main()
