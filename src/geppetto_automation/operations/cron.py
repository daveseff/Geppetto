from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


class CronOperation(Operation):
    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name")
        if not raw_name:
            raise ValueError("cron operation requires a name")
        self.name = str(raw_name)
        self.user = str(spec.get("user", "root"))
        self.target = str(spec.get("target", "cron_d"))
        if self.target not in {"cron_d", "crontab", "crontab_entry"}:
            raise ValueError("cron target must be 'cron_d', 'crontab', or 'crontab_entry'")
        self.content = spec.get("content")
        self.command = spec.get("command")
        if self.target in {"cron_d", "crontab_entry"} and not self.command:
            raise ValueError("cron operation requires a command")
        if self.target == "crontab" and self.content is None:
            raise ValueError("cron operation with target 'crontab' requires content")
        self.schedule = {
            "minute": str(spec.get("minute", "*")),
            "hour": str(spec.get("hour", "*")),
            "day": str(spec.get("day", spec.get("day_of_month", "*"))),
            "month": str(spec.get("month", "*")),
            "weekday": str(spec.get("weekday", spec.get("day_of_week", "*"))),
        }
        self.special = spec.get("special")
        self.env = spec.get("env", {})
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("cron state must be 'present' or 'absent'")
        cron_dir = Path(spec.get("cron_dir", "/etc/cron.d"))
        self.cron_file = cron_dir / f"{self.name}.cron"

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.target == "crontab":
            return self._apply_crontab(host, executor)
        if self.target == "crontab_entry":
            return self._apply_crontab_entry(host, executor)

        if self.state == "absent":
            removed = executor.remove_path(self.cron_file)
            detail = "removed" if removed else "noop"
            return ActionResult(host=host.name, action="cron", changed=removed, details=detail)

        content_lines = []
        for key in sorted(self.env):
            content_lines.append(f"{key}={self.env[key]}")
        schedule = "{minute} {hour} {day} {month} {weekday}".format(**self.schedule)
        content_lines.append(f"{schedule} {self.user} {self.command}")
        content = "\n".join(content_lines) + "\n"

        existing = executor.read_file(self.cron_file)
        if existing == content:
            return ActionResult(host=host.name, action="cron", changed=False, details="noop")

        changed, _ = executor.write_file(self.cron_file, content=content, mode=0o644)
        detail = "updated" if existing else "created"
        return ActionResult(host=host.name, action="cron", changed=changed, details=detail)

    def _apply_crontab(self, host: HostConfig, executor: Executor) -> ActionResult:
        current_result = executor.run(
            ["crontab", "-u", self.user, "-l"], check=False, mutable=False
        )
        no_crontab = (
            current_result.returncode == 1
            and "no crontab" in current_result.stderr.lower()
        )
        if current_result.returncode != 0 and not no_crontab:
            detail = current_result.stderr.strip() or current_result.stdout.strip()
            raise RuntimeError(f"unable to read crontab for {self.user}: {detail}")
        current = current_result.stdout if not no_crontab else None

        if self.state == "absent":
            if current is None:
                return ActionResult(host=host.name, action="cron", changed=False, details="noop")
            executor.run(["crontab", "-u", self.user, "-r"], mutable=True)
            return ActionResult(host=host.name, action="cron", changed=True, details="removed")

        desired = str(self.content)
        if desired and not desired.endswith("\n"):
            desired += "\n"
        if current == desired:
            return ActionResult(host=host.name, action="cron", changed=False, details="noop")

        executor.run(
            ["crontab", "-u", self.user, "-"], mutable=True, input_text=desired
        )
        detail = "updated" if current is not None else "created"
        return ActionResult(host=host.name, action="cron", changed=True, details=detail)

    def _apply_crontab_entry(self, host: HostConfig, executor: Executor) -> ActionResult:
        current_result = executor.run(
            ["crontab", "-u", self.user, "-l"], check=False, mutable=False
        )
        no_crontab = current_result.returncode == 1 and "no crontab" in current_result.stderr.lower()
        if current_result.returncode != 0 and not no_crontab:
            detail = current_result.stderr.strip() or current_result.stdout.strip()
            raise RuntimeError(f"unable to read crontab for {self.user}: {detail}")

        lines = [] if no_crontab else current_result.stdout.splitlines()
        schedule = str(self.special) if self.special else "{minute} {hour} {day} {month} {weekday}".format(**self.schedule)
        desired = f"{schedule} {self.command}"

        if self.state == "absent":
            updated = [line for line in lines if not self._entry_matches(line, desired)]
            if len(updated) == len(lines):
                return ActionResult(host=host.name, action="cron", changed=False, details="noop")
            self._install_crontab(executor, updated)
            return ActionResult(host=host.name, action="cron", changed=True, details="removed")

        missing_env = [f"{key}={value}" for key, value in self.env.items() if f"{key}={value}" not in lines]
        matching_indexes = [index for index, line in enumerate(lines) if self._entry_matches(line, desired)]
        if matching_indexes and not missing_env:
            return ActionResult(host=host.name, action="cron", changed=False, details="noop")

        updated = list(lines)
        if matching_indexes:
            insert_at = matching_indexes[0]
            updated[insert_at:insert_at] = missing_env
        else:
            updated.extend(missing_env)
            updated.append(desired)
        self._install_crontab(executor, updated)
        return ActionResult(host=host.name, action="cron", changed=True, details="updated" if lines else "created")

    def _install_crontab(self, executor: Executor, lines: list[str]) -> None:
        content = "\n".join(lines)
        if content:
            content += "\n"
        executor.run(["crontab", "-u", self.user, "-"], mutable=True, input_text=content)

    @staticmethod
    def _entry_matches(line: str, desired: str) -> bool:
        if desired.startswith("@"):
            return line.strip().split(None, 1) == desired.split(None, 1)
        return line.strip().split(None, 5) == desired.split(None, 5)
