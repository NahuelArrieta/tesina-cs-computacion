"""Standalone tool for generating SUMO human-driver vehicle type distributions."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "type",
    "Accel_Mean",
    "Accel_Std",
    "Decel_Mean",
    "Decel_Std",
}
SAMPLE_COUNT = 50
MINIMUM_ACCELERATION = 0.5
MINIMUM_DECELERATION = 0.5
VEHICLE_LENGTH = "4.5"
MINIMUM_GAP = "2.5"
REACTION_TIME = "1.2"
KRAUSS_SIGMA = "0.5"


def generate_vtypes(
    input_file: Path,
    output_file: Path,
    vehicle_type_percentages: dict[str, float],
    seed: int = 42,
) -> None:
    """Create SUMO vehicle type distributions from configured CSV rows."""
    if seed < 0:
        raise ValueError("seed must be non-negative")
    if not vehicle_type_percentages or not math.isclose(
        sum(vehicle_type_percentages.values()), 100.0
    ):
        raise ValueError("vehicle_type_percentages must sum to 100")
    if any(percentage <= 0 for percentage in vehicle_type_percentages.values()):
        raise ValueError("vehicle_type_percentages must contain positive values")

    parameters = pd.read_csv(input_file)
    missing_columns = REQUIRED_COLUMNS - set(parameters.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CSV is missing required columns: {missing}")

    rng = np.random.default_rng(seed)
    root = ET.Element("additional")
    input_csv_text = str(input_file.resolve())
    try:
        input_csv_text = str(input_file.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        pass
    percentage_text = ", ".join(
        f"{vehicle_type}={percentage:g}"
        for vehicle_type, percentage in vehicle_type_percentages.items()
    )
    root.append(
        ET.Comment(
            f"generated_by=generate_vtypes.py; "
            f"seed={seed}; "
            f"input_csv={input_csv_text}; "
            f"vehicle_type_percentages={percentage_text}"
        )
    )
    for vehicle_type in vehicle_type_percentages:
        type_parameters = parameters.loc[parameters["type"].eq(vehicle_type)]
        if len(type_parameters) != 1:
            raise ValueError(
                f"Expected exactly one row with type == '{vehicle_type}', "
                f"found {len(type_parameters)}"
            )

        row = type_parameters.iloc[0]
        try:
            accel_mean = float(row["Accel_Mean"])
            accel_std = float(row["Accel_Std"])
            decel_mean = float(row["Decel_Mean"])
            decel_std = float(row["Decel_Std"])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{vehicle_type} row contains a non-numeric value in "
                "Accel_Mean, Accel_Std, Decel_Mean, or Decel_Std"
            ) from error

        accel_samples = np.clip(
            rng.normal(accel_mean, accel_std, SAMPLE_COUNT),
            MINIMUM_ACCELERATION,
            None,
        )
        decel_samples = np.clip(
            rng.normal(decel_mean, decel_std, SAMPLE_COUNT),
            MINIMUM_DECELERATION,
            None,
        )

        distribution_id = f"hdv_{vehicle_type.lower().replace(' ', '_')}"
        distribution = ET.SubElement(
            root, "vTypeDistribution", {"id": distribution_id}
        )
        for index, (accel, decel) in enumerate(zip(accel_samples, decel_samples)):
            ET.SubElement(
                distribution,
                "vType",
                {
                    "id": f"{distribution_id}_{index}",
                    "accel": f"{accel:.2f}",
                    "decel": f"{decel:.2f}",
                    "length": VEHICLE_LENGTH,
                    "minGap": MINIMUM_GAP,
                    "tau": REACTION_TIME,
                    "sigma": KRAUSS_SIGMA,
                },
            )

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SUMO human-driver vehicle type distributions"
    )
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_xml", type=Path)
    parser.add_argument(
        "--vehicle-type",
        action="append",
        default=[],
        metavar="TYPE=PERCENTAGE",
        help="Vehicle type and percentage; repeat for each type",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not args.vehicle_type:
        parser.error("at least one --vehicle-type TYPE=PERCENTAGE is required")

    input_csv = args.input_csv.resolve()
    output_xml = args.output_xml.resolve()
    seed = args.seed
    percentages = {}
    for item in args.vehicle_type:
        if "=" not in item:
            parser.error(f"invalid vehicle type percentage: {item}")
        vehicle_type, percentage = item.rsplit("=", 1)
        if not vehicle_type:
            parser.error(f"invalid vehicle type percentage: {item}")
        try:
            percentages[vehicle_type] = float(percentage)
        except ValueError:
            parser.error(f"invalid vehicle type percentage: {item}")

    generate_vtypes(
        input_csv,
        output_xml,
        percentages,
        seed=seed,
    )


if __name__ == "__main__":
    main()
