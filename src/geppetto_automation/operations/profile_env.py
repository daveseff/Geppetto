from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


class ProfileEnvOperation(Operation):
    """Manage environment exports for shells or systemd drop-ins."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        name = spec.get("name")
        if not name:
            raise ValueError("profile_env requires a name")
        self.name = str(name)
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("profile_env state must be 'present' or 'absent'")
        self.format = str(spec.get("format", "profile"))
        if self.format not in {"profile", "systemd"}:
            raise ValueError("profile_env format must be 'profile' or 'systemd'")
        self.variables = spec.get("variables", {})
        if not isinstance(self.variables, dict):
            raise ValueError("profile_env variables must be a mapping")
        if self.state == "present" and not self.variables:
            raise ValueError("profile_env requires at least one variable when state=present")

        default_path = (
            Path(f"/etc/profile.d/{self.name}.sh")
            if self.format == "profile"
            else Path(f"/etc/systemd/system/{self.name}.d/env.conf")
        )
        self.path = Path(spec.get("path") or default_path)
        self.mode = self._parse_mode(spec.get("mode", "0644"))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.state == "absent":
            removed = executor.remove_path(self.path)
            detail = "removed" if removed else "noop"
            return ActionResult(host=host.name, action="profile_env", changed=removed, details=detail)

        content = self._render_content()
        changed, detail = executor.write_file(self.path, content=content, mode=self.mode)
        return ActionResult(host=host.name, action="profile_env", changed=changed, details=detail)

    def _render_content(self) -> str:
        if self.format == "systemd":
            env_parts = []
            for key, value in self.variables.items():
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
                env_parts.append(f'"{key}={escaped}"')
            body = "Environment=" + " ".join(env_parts)
            return "[Service]\n" + body + "\n"

        lines = [f"export {key}={shlex.quote(str(value))}" for key, value in self.variables.items()]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _parse_mode(value: Any) -> int:
        if value is None:
            return 0o644
        if isinstance(value, int):
            return value
        text = str(value).strip()
        base = 8 if text.startswith("0") else 10
        return int(text, base)
