from __future__ import annotations

import logging
import pwd
from dataclasses import dataclass
from typing import Any, Optional

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig

logger = logging.getLogger(__name__)


@dataclass
class UserInfo:
    name: str
    shell: str
    home: str


class UserManager:
    def get(self, username: str) -> UserInfo | None:
        try:
            entry = pwd.getpwnam(username)
        except KeyError:
            return None
        return UserInfo(name=entry.pw_name, shell=entry.pw_shell, home=entry.pw_dir)

    def add(
        self,
        executor: Executor,
        name: str,
        *,
        shell: str | None,
        system: bool,
        create_home: bool,
        comment: str | None,
    ) -> None:
        cmd = ["useradd"]
        if shell:
            cmd += ["--shell", shell]
        if create_home:
            cmd.append("--create-home")
        if system:
            cmd.append("--system")
        if comment:
            cmd += ["--comment", comment]
        cmd.append(name)
        executor.run(cmd)

    def delete(self, executor: Executor, name: str, *, remove_home: bool) -> None:
        cmd = ["userdel"]
        if remove_home:
            cmd.append("--remove")
        cmd.append(name)
        executor.run(cmd)

    def set_shell(self, executor: Executor, name: str, shell: str) -> None:
        executor.run(["usermod", "--shell", shell, name])

    def lock(self, executor: Executor, name: str) -> None:
        executor.run(["passwd", "-l", name])

    def unlock(self, executor: Executor, name: str) -> None:
        executor.run(["passwd", "-u", name])

    def is_locked(self, executor: Executor, name: str) -> bool:
        result = executor.run(["passwd", "-S", name], check=False, mutable=False)
        if result.returncode != 0:
            return False
        parts = result.stdout.strip().split()
        if len(parts) < 2:
            return False
        return parts[1].upper().startswith("L")


class UserOperation(Operation):
    """Ensure user accounts exist with optional ssh locking."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name")
        if not raw_name:
            raise ValueError("user operation requires a name")
        self.name = str(raw_name)
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("user operation state must be 'present' or 'absent'")
        self.shell = spec.get("shell")
        self.system = bool(self._to_bool(spec.get("system", False)))
        self.create_home = self._bool_with_default(spec.get("create_home"), True)
        self.remove_home = bool(self._to_bool(spec.get("remove_home", False)))
        self.locked: Optional[bool] = self._to_bool(spec.get("locked"))
        self.comment = spec.get("comment")
        self.manager = UserManager()

    @staticmethod
    def _to_bool(value: Any | None) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1", "on"}:
                return True
            if lowered in {"false", "no", "0", "off"}:
                return False
            raise ValueError(f"Unable to interpret boolean value '{value}'")
        return bool(value)

    @staticmethod
    def _bool_with_default(value: Any | None, default: bool) -> bool:
        if value is None:
            return default
        result = UserOperation._to_bool(value)
        return default if result is None else bool(result)

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        info = self.manager.get(self.name)
        changes: list[str] = []

        if self.state == "present":
            if not info:
                logger.debug("Creating user %s", self.name)
                self.manager.add(
                    executor,
                    self.name,
                    shell=str(self.shell) if self.shell else None,
                    system=self.system,
                    create_home=self.create_home,
                    comment=str(self.comment) if self.comment else None,
                )
                changes.append("created")
            else:
                if self.shell and info.shell != self.shell:
                    logger.debug("Updating shell for %s", self.name)
                    self.manager.set_shell(executor, self.name, str(self.shell))
                    changes.append("shell")

            if self.locked is not None:
                locked = self.manager.is_locked(executor, self.name)
                if self.locked and not locked:
                    logger.debug("Locking password for %s", self.name)
                    self.manager.lock(executor, self.name)
                    changes.append("locked")
                elif not self.locked and locked:
                    logger.debug("Unlocking password for %s", self.name)
                    self.manager.unlock(executor, self.name)
                    changes.append("unlocked")

        else:  # state == absent
            if info:
                logger.debug("Removing user %s", self.name)
                self.manager.delete(executor, self.name, remove_home=self.remove_home)
                changes.append("removed")

        changed = bool(changes)
        detail = ", ".join(changes) if changes else "noop"
        return ActionResult(host=host.name, action="user", changed=changed, details=detail)
