from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from typing import Any

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig

logger = logging.getLogger(__name__)


@dataclass
class SystemCtl:
    executable: str = "systemctl"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def is_enabled(self, executor: Executor, service: str) -> bool:
        result = executor.run([self.executable, "is-enabled", service], check=False, mutable=False)
        return result.returncode == 0

    def is_active(self, executor: Executor, service: str) -> bool:
        result = executor.run([self.executable, "is-active", service], check=False, mutable=False)
        return result.returncode == 0

    def enable(self, executor: Executor, service: str) -> None:
        executor.run([self.executable, "enable", service])

    def disable(self, executor: Executor, service: str) -> None:
        executor.run([self.executable, "disable", service])

    def start(self, executor: Executor, service: str) -> None:
        executor.run([self.executable, "start", service])

    def stop(self, executor: Executor, service: str) -> None:
        executor.run([self.executable, "stop", service])

    def restart(self, executor: Executor, service: str) -> None:
        executor.run([self.executable, "restart", service])


class ServiceOperation(Operation):
    """Manage systemd services."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name")
        if not raw_name:
            raise ValueError("service operation requires a name")
        self.name = str(raw_name)
        self._enabled = self._coerce_bool(spec.get("enabled"))
        self._state = spec.get("state")
        self.restart = bool(self._coerce_bool(spec.get("restart", False)))
        if self._state not in {None, "running", "stopped"}:
            raise ValueError("service state must be 'running' or 'stopped'")
        self.systemctl = SystemCtl()

    @staticmethod
    def _coerce_bool(value: Any | None) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "on", "1"}:
                return True
            if lowered in {"false", "no", "off", "0"}:
                return False
            raise ValueError(f"Unable to interpret boolean value '{value}'")
        return bool(value)

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if not self.systemctl.available():
            raise RuntimeError("systemctl is not available on this host")

        changes: list[str] = []

        if self._enabled is not None:
            should_enable = bool(self._enabled)
            enabled = self.systemctl.is_enabled(executor, self.name)
            if should_enable and not enabled:
                logger.debug("Enabling service %s", self.name)
                if not executor.dry_run:
                    self.systemctl.enable(executor, self.name)
                changes.append("enabled")
            elif not should_enable and enabled:
                logger.debug("Disabling service %s", self.name)
                if not executor.dry_run:
                    self.systemctl.disable(executor, self.name)
                changes.append("disabled")

        if self._state is not None:
            desired = self._state
            active = self.systemctl.is_active(executor, self.name)
            if desired == "running" and not active:
                logger.debug("Starting service %s", self.name)
                if not executor.dry_run:
                    self.systemctl.start(executor, self.name)
                changes.append("started")
            elif desired == "stopped" and active:
                logger.debug("Stopping service %s", self.name)
                if not executor.dry_run:
                    self.systemctl.stop(executor, self.name)
                changes.append("stopped")

        if self.restart:
            logger.debug("Restarting service %s", self.name)
            if not executor.dry_run:
                self.systemctl.restart(executor, self.name)
            changes.append("restarted")

        changed = bool(changes)
        detail = ", ".join(changes) if changes else "noop"
        return ActionResult(host=host.name, action="service", changed=changed, details=detail)
