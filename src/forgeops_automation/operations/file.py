from __future__ import annotations

import os
import shutil
from pathlib import Path
from string import Template

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
        raw_content = spec.get("content")
        self.content = "" if raw_content is None else str(raw_content)
        self.mode = self._parse_mode(spec.get("mode"))
        self.template = spec.get("template")
        self.variables = spec.get("variables", {})
        self.plan_dir = spec.get("_plan_dir")
        self.link_target = spec.get("link_target") or spec.get("target")
        if self.template is not None:
            self.template = str(self.template)
        if not isinstance(self.variables, dict):
            raise ValueError("file operation variables must be a mapping")
        if self.plan_dir is not None:
            self.plan_dir = Path(str(self.plan_dir))
        if self.link_target is not None:
            self.link_target = str(self.link_target)

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.link_target:
            return self._apply_symlink(executor)
        if self.state == "present":
            content = self._render_content(host)
            changed, detail = executor.write_file(self.path, content=content, mode=self.mode)
        else:
            removed = executor.remove_path(self.path)
            detail = "removed" if removed else "noop"
            changed = removed
        return ActionResult(host=host.name, action="file", changed=changed, details=detail)

    def _render_content(self, host: HostConfig) -> str:
        if not self.template:
            return self.content
        template_path = Path(self.template).expanduser()
        if not template_path.is_absolute() and self.plan_dir is not None:
            template_path = self.plan_dir / template_path
        template_text = template_path.read_text()
        context: dict[str, object] = dict(host.variables)
        for key, value in self.variables.items():
            context[key] = value
        template = Template(template_text)
        return template.safe_substitute(context)

    def _apply_symlink(self, executor: Executor) -> ActionResult:
        host_name = executor.host.name
        if self.state == "absent":
            removed = self._remove_path(executor)
            detail = "removed" if removed else "noop"
            return ActionResult(host=host_name, action="file", changed=removed, details=detail)

        current_target = None
        try:
            if self.path.is_symlink():
                current_target = os.readlink(self.path)
        except OSError:
            current_target = None

        if current_target == self.link_target:
            return ActionResult(host=host_name, action="file", changed=False, details="noop")

        if not executor.dry_run:
            if self.path.exists() or self.path.is_symlink():
                if self.path.is_dir() and not self.path.is_symlink():
                    shutil.rmtree(self.path)
                else:
                    self.path.unlink(missing_ok=True)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(self.link_target, self.path)
        detail = f"link->{self.link_target}"
        return ActionResult(host=host_name, action="file", changed=True, details=detail)

    def _remove_path(self, executor: Executor) -> bool:
        if not self.path.exists() and not self.path.is_symlink():
            return False
        if executor.dry_run:
            return True
        if self.path.is_dir() and not self.path.is_symlink():
            shutil.rmtree(self.path)
        else:
            self.path.unlink(missing_ok=True)
        return True

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
