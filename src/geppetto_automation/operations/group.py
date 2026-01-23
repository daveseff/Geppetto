from __future__ import annotations

import logging
import grp
from dataclasses import dataclass
from typing import Any, Optional

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig

logger = logging.getLogger(__name__)


@dataclass
class GroupInfo:
    name: str
    gid: int


class GroupManager:
    def get(self, name: str) -> Optional[GroupInfo]:
        try:
            entry = grp.getgrnam(name)
        except KeyError:
            return None
        return GroupInfo(name=entry.gr_name, gid=entry.gr_gid)

    def add(self, executor: Executor, name: str, *, gid: Optional[int]) -> None:
        cmd = ["groupadd"]
        if gid is not None:
            cmd += ["--gid", str(gid)]
        cmd.append(name)
        executor.run(cmd)

    def delete(self, executor: Executor, name: str) -> None:
        executor.run(["groupdel", name])

    def set_gid(self, executor: Executor, name: str, gid: int) -> None:
        executor.run(["groupmod", "--gid", str(gid), name])


class GroupOperation(Operation):
    """Ensure groups exist with optional gid enforcement."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name")
        if not raw_name:
            raise ValueError("group operation requires a name")
        self.name = str(raw_name)
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("group operation state must be 'present' or 'absent'")
        self.gid = self._to_int(spec.get("gid"))
        self.manager = GroupManager()

    @staticmethod
    def _to_int(value: Optional[Any]) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        if not text.isdigit():
            raise ValueError(f"Unable to interpret integer value '{value}'")
        return int(text)

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        info = self.manager.get(self.name)
        changes: list[str] = []

        if self.state == "present":
            if not info:
                logger.debug("Creating group %s", self.name)
                self.manager.add(executor, self.name, gid=self.gid)
                changes.append("created")
            else:
                if self.gid is not None and info.gid != self.gid:
                    logger.debug("Updating gid for %s", self.name)
                    self.manager.set_gid(executor, self.name, self.gid)
                    changes.append("gid")
        else:
            if info:
                logger.debug("Removing group %s", self.name)
                self.manager.delete(executor, self.name)
                changes.append("removed")

        changed = bool(changes)
        detail = ", ".join(changes) if changes else "noop"
        return ActionResult(host=host.name, action="group", changed=changed, details=detail)
