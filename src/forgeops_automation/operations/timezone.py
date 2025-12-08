from __future__ import annotations

import filecmp
import os
from pathlib import Path
from typing import Any

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


class TimezoneOperation(Operation):
    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        zone = spec.get("zone") or spec.get("name")
        if not zone:
            raise ValueError("timezone operation requires a zone")
        self.zone = str(zone)
        self.localtime_path = Path(spec.get("localtime_path", "/etc/localtime"))
        self.zoneinfo_dir = Path(spec.get("zoneinfo_dir", "/usr/share/zoneinfo"))
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("timezone state must be 'present' or 'absent'")
        self.manage_etc_timezone = bool(spec.get("manage_etc_timezone", False))
        self.etc_timezone = Path(spec.get("etc_timezone_path", "/etc/timezone"))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.state == "absent":
            changed = False
            details: list[str] = []
            if self.localtime_path.exists() or self.localtime_path.is_symlink():
                changed = True
                details.append("localtime")
                if not executor.dry_run:
                    self.localtime_path.unlink(missing_ok=True)
            if self.manage_etc_timezone and self.etc_timezone.exists():
                changed = True
                details.append("etc_timezone")
                if not executor.dry_run:
                    self.etc_timezone.unlink(missing_ok=True)
            detail = ", ".join(details) if details else "noop"
            return ActionResult(host=host.name, action="timezone", changed=changed, details=detail)

        target_file = self.zoneinfo_dir / self.zone
        if not target_file.exists():
            raise FileNotFoundError(f"Zone file {target_file} does not exist")

        changed = False
        detail_parts: list[str] = []

        if not self._is_current_timezone(target_file):
            changed = True
            detail_parts.append(f"zone->{self.zone}")
            if not executor.dry_run:
                self.localtime_path.parent.mkdir(parents=True, exist_ok=True)
                if self.localtime_path.exists() or self.localtime_path.is_symlink():
                    self.localtime_path.unlink(missing_ok=True)
                os.symlink(target_file, self.localtime_path)

        if self.manage_etc_timezone:
            current = self.etc_timezone.read_text().strip() if self.etc_timezone.exists() else ""
            if current != self.zone:
                changed = True
                detail_parts.append("etc_timezone")
                if not executor.dry_run:
                    self.etc_timezone.parent.mkdir(parents=True, exist_ok=True)
                    self.etc_timezone.write_text(f"{self.zone}\n")

        detail = ", ".join(detail_parts) if detail_parts else "noop"
        return ActionResult(host=host.name, action="timezone", changed=changed, details=detail)

    def _is_current_timezone(self, target: Path) -> bool:
        if self.localtime_path.is_symlink():
            try:
                return os.readlink(self.localtime_path) == str(target)
            except OSError:
                return False
        if not self.localtime_path.exists():
            return False
        try:
            return filecmp.cmp(self.localtime_path, target, shallow=False)
        except OSError:
            return False
