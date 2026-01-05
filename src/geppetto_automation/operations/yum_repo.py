from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


class YumRepoOperation(Operation):
    """Manage yum/dnf repo stanzas under /etc/yum.repos.d."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name") or spec.get("id") or spec.get("repoid") or spec.get("repository")
        if not raw_name:
            raise ValueError("yum_repo requires a name")
        self.name = str(raw_name)
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("yum_repo state must be 'present' or 'absent'")

        self.baseurl = spec.get("baseurl")
        self.mirrorlist = spec.get("mirrorlist")
        if self.state == "present" and not (self.baseurl or self.mirrorlist):
            raise ValueError("yum_repo requires baseurl or mirrorlist when state=present")

        self.enabled = _coerce_bool(spec.get("enabled", True))
        self.gpgcheck = _coerce_bool(spec.get("gpgcheck", True))
        self.repo_gpgcheck = spec.get("repo_gpgcheck")
        if self.repo_gpgcheck is not None:
            self.repo_gpgcheck = _coerce_bool(self.repo_gpgcheck)
        self.gpgkey = spec.get("gpgkey")
        self.description = spec.get("description", self.name)
        self.metadata_expire = spec.get("metadata_expire")
        self.options: Dict[str, Any] = spec.get("options", {}) or {}
        if not isinstance(self.options, dict):
            raise ValueError("yum_repo options must be a mapping")
        self.path = Path(spec.get("path") or f"/etc/yum.repos.d/{self.name}.repo")
        self.mode = self._parse_mode(spec.get("mode", "0644"))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.state == "absent":
            removed = executor.remove_path(self.path)
            detail = "removed" if removed else "noop"
            return ActionResult(host=host.name, action="yum_repo", changed=removed, details=detail)

        content = self._render()
        changed, detail = executor.write_file(self.path, content=content, mode=self.mode)
        return ActionResult(host=host.name, action="yum_repo", changed=changed, details=detail)

    def _render(self) -> str:
        lines = [f"[{self.name}]"]
        lines.append(f"name={self.description}")
        if self.baseurl:
            lines.append(f"baseurl={self.baseurl}")
        if self.mirrorlist:
            lines.append(f"mirrorlist={self.mirrorlist}")
        lines.append(f"enabled={_bool_to_int(self.enabled)}")
        lines.append(f"gpgcheck={_bool_to_int(self.gpgcheck)}")
        if self.repo_gpgcheck is not None:
            lines.append(f"repo_gpgcheck={_bool_to_int(bool(self.repo_gpgcheck))}")
        if self.gpgkey:
            lines.append(f"gpgkey={self.gpgkey}")
        if self.metadata_expire:
            lines.append(f"metadata_expire={self.metadata_expire}")
        for key, value in sorted(self.options.items()):
            lines.append(f"{key}={value}")
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


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _bool_to_int(value: bool) -> int:
    return 1 if value else 0
