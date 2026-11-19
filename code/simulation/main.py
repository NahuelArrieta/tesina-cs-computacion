"""Run one or all strategies for an experiment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from simulation.simulator import run_from_manifest


STRATEGIES = ("m0", "m1", "m2", "m3")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one or all strategies for an experiment"
    )
    parser.add_argument("experiment", help="Experiment name")
    parser.add_argument("--strategy", choices=STRATEGIES)
    visualization_group = parser.add_mutually_exclusive_group()
    visualization_group.add_argument(
        "--gui-overlay",
        action="store_const",
        const="gui-overlay",
        dest="visualization_mode",
        help="Color the subgraph streets as overlays in SUMO-GUI.",
    )
    args = parser.parse_args()

    experiment_directory = Path(
        os.environ.get(
            "EXPERIMENT_DIR",
            str(Path(__file__).resolve().parents[2] / "experiments"),
        )
    ).expanduser().resolve()
    manifest_file = experiment_directory / args.experiment / "manifest.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Experiment manifest not found: {manifest_file}")

    strategies = [args.strategy] if args.strategy else list(STRATEGIES)
    for strategy in strategies:
        run_from_manifest(
            manifest_file,
            strategy,
            visualization_mode=args.visualization_mode,
        )
        print(f"Completed strategy {strategy}")


if __name__ == "__main__":
    main()
