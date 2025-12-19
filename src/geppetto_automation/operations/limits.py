from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


class LimitsOperation(Operation):
    """Manage /etc/security/limits.d entries."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        name = spec.get("name")
        if not name:
            raise ValueError("limits operation requires a name (used for the file name)")
        self.name = str(name)
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("limits state must be 'present' or 'absent'")
        self.mode = self._parse_mode(spec.get("mode", "0644"))
        self.path = Path(spec.get("path") or f"/etc/security/limits.d/{self.name}.conf")
        self.entries = self._collect_entries(spec)

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.state == "absent":
            removed = executor.remove_path(self.path)
            detail = "removed" if removed else "noop"
            return ActionResult(host=host.name, action="limits", changed=removed, details=detail)

        content = self._render_entries()
        changed, detail = executor.write_file(self.path, content=content, mode=self.mode)
        return ActionResult(host=host.name, action="limits", changed=changed, details=detail)

    def _collect_entries(self, spec: dict[str, Any]) -> list[tuple[str, str, str, str]]:
        entries = spec.get("entries")
        parsed: list[tuple[str, str, str, str]] = []

        if entries is None:
            domain, limit_type, item, value = (
                spec.get("domain"),
                spec.get("type"),
                spec.get("item"),
                spec.get("value"),
            )
            if all(v is not None for v in (domain, limit_type, item, value)):
                entries = [{"domain": domain, "type": limit_type, "item": item, "value": value}]

        if entries is None:
            raise ValueError("limits requires either entries[] or domain/type/item/value")

        if not isinstance(entries, list):
            raise ValueError("limits entries must be a list")

        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each limits entry must be a mapping")
            domain = entry.get("domain")
            limit_type = entry.get("type")
            item = entry.get("item")
            value = entry.get("value")
            if any(v is None for v in (domain, limit_type, item, value)):
                raise ValueError("limits entry requires domain, type, item, and value")
            parsed.append((str(domain), str(limit_type), str(item), str(value)))

        return parsed

    def _render_entries(self) -> str:
        lines = [f"{d} {t} {i} {v}" for d, t, i, v in self.entries]
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
