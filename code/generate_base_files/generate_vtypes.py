"""Generate SUMO human-driver vehicle type distributions."""

from __future__ import annotations

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
    "Speed_Mean",
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
) -> None:
    """Create SUMO vehicle type distributions from configured CSV rows."""
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

    root = ET.Element("additional")
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
            max_speed = float(row["Speed_Mean"])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{vehicle_type} row contains a non-numeric value in "
                "Accel_Mean, Accel_Std, Decel_Mean, Decel_Std, or Speed_Mean"
            ) from error

        accel_samples = np.clip(
            np.random.normal(accel_mean, accel_std, SAMPLE_COUNT),
            MINIMUM_ACCELERATION,
            None,
        )
        decel_samples = np.clip(
            np.random.normal(decel_mean, decel_std, SAMPLE_COUNT),
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
                    "maxSpeed": f"{max_speed:.2f}",
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
