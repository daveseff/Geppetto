from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from .config import load_config
from .inventory import InventoryLoader
from .runner import TaskRunner
from .state import StateStore
from .types import ActionResult


class Ansi:
    GREEN = "\033[92m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def colorize(text: str, color: str | None) -> str:
    if not color:
        return text
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"{color}{text}{Ansi.RESET}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ForgeOps automation runner")
    parser.add_argument(
        "plan",
        nargs="?",
        default=None,
        type=Path,
        help="Path to a plan file (default from config or /etc/forgeops/plan.fops)",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        help="Location for plan state (default: plan + .state.json)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/etc/forgeops/main.conf"),
        help="Path to forgeops config file (default: /etc/forgeops/main.conf)",
    )
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

    cfg = load_config(args.config)
    plan_path = args.plan or cfg.plan
    loader = InventoryLoader()
    plan = loader.load(plan_path)

    state_path = args.state_file or cfg.state_file
    if not state_path:
        state_path = plan_path.with_name(plan_path.name + ".state.json")

    state_store = None if args.dry_run else StateStore(state_path)

    runner = TaskRunner(plan, dry_run=args.dry_run, state_store=state_store)
    results = runner.run()

    for result in results:
        print(format_result(result))

    return 0


def format_result(result: ActionResult) -> str:
    status = "changed" if result.changed else "ok"
    color: str | None = None
    if result.failed:
        status = "failed"
        color = Ansi.RED
    elif result.changed:
        color = Ansi.GREEN
    elif "noop" in result.details.lower():
        color = Ansi.BLUE
    else:
        color = Ansi.BLUE
    line = f"{result.host}::{result.action} {status} - {result.details}"
    return colorize(line, color)


if __name__ == "__main__":
    raise SystemExit(main())
