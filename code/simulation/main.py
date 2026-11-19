"""Run one or all strategies for an experiment."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument(
        "--penetration",
        type=float,
        help="CAV penetration rate between 0 and 1",
    )
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

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    configured_penetrations = [
        float(penetration) for penetration in manifest["cav_penetrations"]
    ]
    if args.penetration is not None:
        if not 0.0 < args.penetration <= 1.0:
            raise ValueError("penetration must be greater than 0 and at most 1")
        if not any(
            abs(args.penetration - configured) < 1e-9
            for configured in configured_penetrations
        ):
            raise ValueError(
                f"Penetration {args.penetration:g} is not configured "
                "in cav_penetrations"
            )

    strategies = [args.strategy] if args.strategy else list(STRATEGIES)
    if args.strategy == "m0" and args.penetration is not None:
        raise ValueError("m0 always runs at penetration 0 and does not accept --penetration")

    if args.strategy == "m0":
        runs = [(0.0, "m0")]
    else:
        selected_penetrations = (
            [args.penetration]
            if args.penetration is not None
            else [rate for rate in configured_penetrations if rate > 0.0]
        )
        runs = [
            (penetration, strategy)
            for penetration in selected_penetrations
            for strategy in strategies
            if strategy != "m0"
        ]
        if args.strategy is None:
            runs.insert(0, (0.0, "m0"))

    for penetration, strategy in runs:
        percentage = int(round(penetration * 100))
        run_from_manifest(
            manifest_file,
            strategy,
            penetration,
            visualization_mode=args.visualization_mode,
        )
        print(f"Completed penetration p{percentage}, strategy {strategy}")


if __name__ == "__main__":
    main()
