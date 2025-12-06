from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


class SysctlOperation(Operation):
    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name")
        if not raw_name:
            raise ValueError("sysctl operation requires a name")
        self.name = str(raw_name)
        if "=" in self.name:
            raise ValueError("sysctl name should not contain '='")
        raw_value = spec.get("value")
        if raw_value is None:
            raise ValueError("sysctl operation requires a value")
        self.value = str(raw_value)
        self.persist = bool(spec.get("persist", True))
        default_conf = f"/etc/sysctl.d/{self.name.replace('.', '_')}.conf"
        self.conf_file = Path(spec.get("conf_file", default_conf))
        self.apply_runtime = bool(spec.get("apply_runtime", True))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        changed = False
        details: list[str] = []

        if self.apply_runtime:
            executor.run(["sysctl", "-w", f"{self.name}={self.value}"])
            details.append("runtime")
            changed = True

        if self.persist:
            content = f"{self.name} = {self.value}\n"
            existing = self.conf_file.read_text() if self.conf_file.exists() else ""
            if existing != content:
                changed = True
                details.append("persist")
                if not executor.dry_run:
                    self.conf_file.parent.mkdir(parents=True, exist_ok=True)
                    self.conf_file.write_text(content)
            else:
                changed = changed or False
        else:
            changed = changed or self.apply_runtime

        detail = ", ".join(details) if details else "noop"
        return ActionResult(host=host.name, action="sysctl", changed=changed, details=detail)
