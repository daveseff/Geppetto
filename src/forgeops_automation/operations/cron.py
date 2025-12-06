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
        self.command = spec.get("command")
        if not self.command:
            raise ValueError("cron operation requires a command")
        self.schedule = {
            "minute": str(spec.get("minute", "*")),
            "hour": str(spec.get("hour", "*")),
            "day": str(spec.get("day", spec.get("day_of_month", "*"))),
            "month": str(spec.get("month", "*")),
            "weekday": str(spec.get("weekday", spec.get("day_of_week", "*"))),
        }
        self.env = spec.get("env", {})
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("cron state must be 'present' or 'absent'")
        cron_dir = Path(spec.get("cron_dir", "/etc/cron.d"))
        self.cron_file = cron_dir / f"{self.name}.cron"

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
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
