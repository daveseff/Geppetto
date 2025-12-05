from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from .inventory import InventoryLoader
from .runner import TaskRunner


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ForgeOps automation runner")
    parser.add_argument("plan", type=Path, help="Path to a plan TOML file")
    parser.add_argument("--dry-run", action="store_true", help="Calculate changes without executing")
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO)",
    )
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(levelname)s %(name)s - %(message)s",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    loader = InventoryLoader()
    plan = loader.load(args.plan)

    runner = TaskRunner(plan, dry_run=args.dry_run)
    results = runner.run()

    for result in results:
        status = "changed" if result.changed else "ok"
        print(f"{result.host}::{result.action} {status} - {result.details}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
