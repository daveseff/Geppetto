from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from .config import load_config
from .dsl import DSLParseError
from .inventory import InventoryLoader
from .runner import TaskRunner
from .state import StateStore
from .types import ActionResult


class Ansi:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    ORANGE = "\033[38;5;208m"
    RESET = "\033[0m"


def colorize(text: str, color: Optional[str]) -> str:
    if not color:
        return text
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"{color}{text}{Ansi.RESET}"

_last_progress_len = 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    cfg = load_config(args.config)
    _apply_aws_env(cfg)
    plan_path = args.plan or cfg.plan
    loader = InventoryLoader()
    try:
        plan = loader.load(plan_path)
    except (DSLParseError, ValueError) as exc:
        _clear_progress()
        print(colorize(f"Plan validation failed: {exc}", Ansi.RED), file=sys.stderr)
        return 1

    state_path = args.state_file or cfg.state_file
    if not state_path:
        state_path = plan_path.with_name(plan_path.name + ".state.json")

    state_store = None if args.dry_run else StateStore(state_path)

    runner = TaskRunner(
        plan,
        dry_run=args.dry_run,
        state_store=state_store,
        progress_callback=print_progress,
    )
    results = runner.run()

    effective_level = logging.getLogger().getEffectiveLevel()
    summary = Summary()
    for result in results:
        _clear_progress()
        summary.add(result)
        if not should_display_result(result, effective_level):
            continue
        print(format_result(result))

    _clear_progress()
    print(summary.render())

    return 0


def format_result(result: ActionResult) -> str:
    status = "changed" if result.changed else "ok"
    color: Optional[str] = None
    if result.failed:
        if "unknown operation" in result.details.lower():
            status = "unknown"
            color = Ansi.ORANGE
        else:
            status = "failed"
            color = Ansi.RED
    elif result.changed:
        color = Ansi.GREEN
    elif "noop" in result.details.lower():
        color = Ansi.BLUE
    else:
        color = Ansi.BLUE
    resource = f"[{result.resource}]" if result.resource else ""
    line = f"{result.host}::{result.action}{resource} {status} - {result.details}"
    return colorize(line, color)


def should_display_result(result: ActionResult, log_level: int) -> bool:
    if result.failed or result.changed:
        return True
    return log_level <= logging.DEBUG


def print_progress(host, action) -> None:
    global _last_progress_len
    resource = _progress_resource(action.data)
    suffix = f"[{resource}]" if resource else ""
    line = f"{host.name}::{action.type}{suffix} pending..."
    _last_progress_len = len(line)
    print(colorize(line, Ansi.YELLOW), end="\r", flush=True)


def _progress_resource(data: dict) -> Optional[str]:
    for key in ("resource", "name", "path", "mount_point", "user", "service"):
        value = data.get(key)
        if value:
            return str(value)
    pkgs = data.get("packages")
    if isinstance(pkgs, (list, tuple)) and pkgs:
        rendered = ", ".join(str(p) for p in pkgs[:3])
        if len(pkgs) > 3:
            rendered += ", ..."
        return rendered
    return None


def _clear_progress() -> None:
    global _last_progress_len
    if _last_progress_len:
        print(" " * _last_progress_len, end="\r", flush=True)
        _last_progress_len = 0


def _apply_aws_env(cfg) -> None:
    if getattr(cfg, "aws_profile", None) and "AWS_PROFILE" not in os.environ:
        os.environ["AWS_PROFILE"] = cfg.aws_profile  # type: ignore[assignment]
    if getattr(cfg, "aws_region", None):
        if "AWS_REGION" not in os.environ:
            os.environ["AWS_REGION"] = cfg.aws_region  # type: ignore[assignment]
        if "AWS_DEFAULT_REGION" not in os.environ:
            os.environ["AWS_DEFAULT_REGION"] = cfg.aws_region  # type: ignore[assignment]


class Summary:
    def __init__(self) -> None:
        self.changes = 0
        self.additions = 0
        self.rollbacks = 0
        self.failures = 0

    def add(self, result: ActionResult) -> None:
        if result.failed:
            self.failures += 1
            return
        if not result.changed:
            return
        self.changes += 1
        if _looks_like_rollback(result):
            self.rollbacks += 1
        else:
            self.additions += 1

    def render(self) -> str:
        parts = [
            f"Changes: {self.changes}",
            f"Additions: {self.additions}",
            f"Rollbacks: {self.rollbacks}",
            f"Failures: {self.failures}",
        ]
        text = " | ".join(parts)
        color = Ansi.GREEN if self.failures == 0 else Ansi.RED
        return colorize(text, color)


def _looks_like_rollback(result: ActionResult) -> bool:
    text = (result.details or "").lower()
    rollback_tokens = {"remove", "removed", "absent", "deleted", "stopped", "disabled", "unmounted"}
    return any(token in text for token in rollback_tokens)


if __name__ == "__main__":
    raise SystemExit(main())
