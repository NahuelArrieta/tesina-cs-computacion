"""Generate the complete base-file demand matrix from a JSON configuration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_base_files.generate_demand import generate_demand


def generate_matrix(config_file: Path) -> list[dict[str, int | float | str]]:
    """Generate one route file for every configured scenario."""
    config_file = config_file.resolve()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    network_file = (config_file.parent / config["network"]).resolve()
    output_directory = network_file.parent / "routes" / config_file.stem
    output_directory.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, int | float | str]] = []

    for seed in config["seeds"]:
        for penetration in config["cav_penetrations"]:
            percentage = int(round(float(penetration) * 100))
            scenario = f"seed{seed}_cav{percentage:02d}"
            route_file = output_directory / f"{scenario}.rou.xml"
            manifest = generate_demand(
                network_file=network_file,
                output_file=route_file,
                period=float(config["period_s"]),
                begin=float(config["begin_s"]),
                end=float(config["end_s"]),
                seed=int(seed),
                cav_penetration=float(penetration),
            )
            manifest["scenario"] = scenario
            manifest["config"] = config_file.name
            manifests.append(manifest)

    (output_directory / "manifest.json").write_text(
        json.dumps(manifests, indent=2) + "\n", encoding="utf-8"
    )
    return manifests


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the base-file demand matrix"
    )
    parser.add_argument(
        "--config", type=Path, required=True, help="Base-file JSON configuration"
    )
    args = parser.parse_args()
    manifests = generate_matrix(args.config)
    print(f"Generated {len(manifests)} base-file scenarios")


if __name__ == "__main__":
    main()
