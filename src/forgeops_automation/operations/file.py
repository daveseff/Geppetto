from __future__ import annotations

from pathlib import Path

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


class FileOperation(Operation):
    """Ensure files exist with the requested contents."""

    def __init__(self, spec: dict[str, object]):
        super().__init__(spec)
        raw_path = spec.get("path")
        if not raw_path:
            raise ValueError("file operation requires a path")
        self.path = Path(str(raw_path))
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("file operation state must be 'present' or 'absent'")
        self.content = str(spec.get("content", ""))
        self.mode = self._parse_mode(spec.get("mode"))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.state == "present":
            changed, detail = executor.write_file(self.path, content=self.content, mode=self.mode)
        else:
            removed = executor.remove_path(self.path)
            detail = "removed" if removed else "noop"
            changed = removed
        return ActionResult(host=host.name, action="file", changed=changed, details=detail)

    @staticmethod
    def _parse_mode(value: object | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        base = 8 if text.startswith("0") else 10
        return int(text, base)
