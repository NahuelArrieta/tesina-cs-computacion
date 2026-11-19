"""Generate the complete base-file demand matrix from a JSON configuration."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_base_files.generate_demand import generate_demand
def generate_routes(
    config: dict[str, object],
    network_directory: Path,
    vtype_directory: Path,
    experiment_directory: Path,
    experiment_name: str,
) -> list[Path]:
    """Generate one standalone route file per CAV penetration."""
    network_name = str(config["network"])
    if Path(network_name).name != network_name or network_name in ("", ".", ".."):
        raise ValueError("network must be a file name")
    network_file = (network_directory / network_name).resolve()
    if not network_file.is_file():
        raise FileNotFoundError(f"Network file not found: {network_file}")
    vtypes_name = str(config["vtypes"])
    if Path(vtypes_name).name != vtypes_name or vtypes_name in ("", ".", ".."):
        raise ValueError("vtypes must be a file name")
    vtypes_file = (vtype_directory / vtypes_name).resolve()
    if not vtypes_file.is_file():
        raise FileNotFoundError(f"VTypes file not found: {vtypes_file}")

    output_directory = experiment_directory / experiment_name / "routes"
    output_directory.mkdir(parents=True, exist_ok=True)
    seed = int(config["routes_seed"])
    if seed < 0:
        raise ValueError("seed must be non-negative")
    route_files: list[Path] = []
    for penetration in config["cav_penetrations"]:
        percentage = int(round(float(penetration) * 100))
        route_file = output_directory / f"penetration_{percentage}.rou.xml"
        generate_demand(
            network_file=network_file,
            output_file=route_file,
            begin=float(config["begin_s"]),
            end=float(config["end_s"]),
            period=float(config["period_s"]),
            seed=seed,
            cav_penetration=float(penetration),
            vtypes_file=vtypes_file,
        )
        route_files.append(route_file)
    return route_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the base-file demand matrix"
    )
    parser.add_argument("experiment", help="Experiment name")
    args = parser.parse_args()

    experiment_name = args.experiment
    if Path(experiment_name).name != experiment_name or experiment_name in ("", ".", ".."):
        raise ValueError("Experiment name must be a single directory name")

    experiment_directory = Path(
        os.environ.get(
            "EXPERIMENT_DIR",
            str(Path(__file__).resolve().parents[2] / "experiments"),
        )
    ).expanduser().resolve()
    network_directory = Path(
        os.environ.get(
            "NETWORK_DIR",
            str(Path(__file__).resolve().parents[2] / "source files" / "networks"),
        )
    ).expanduser().resolve()
    vtype_directory = Path(
        os.environ.get(
            "VTYPE_DIR",
            str(Path(__file__).resolve().parents[2] / "source files" / "car distribution"),
        )
    ).expanduser().resolve()
    manifest_file = experiment_directory / experiment_name / "manifest.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Experiment manifest not found: {manifest_file}")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("experiment") != experiment_name:
        raise ValueError(
            f"Manifest experiment '{manifest.get('experiment')}' "
            f"does not match '{experiment_name}'"
        )
    route_files = generate_routes(
        manifest,
        network_directory,
        vtype_directory,
        experiment_directory,
        experiment_name,
    )
    print(f"Generated {len(route_files)} route files")


if __name__ == "__main__":
    main()
