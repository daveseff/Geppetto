from __future__ import annotations

import os
import shutil
from pathlib import Path
from string import Template
from typing import Optional
import re
import pwd
import grp

from .base import Operation
from ..executors import Executor
from ..secrets import SecretResolver
from ..types import ActionResult, HostConfig

# Optional dependency; resolved at render time if Jinja syntax is detected
try:  # pragma: no cover
    import jinja2
except Exception:  # pragma: no cover
    jinja2 = None

class FileOperation(Operation):
    """Ensure files exist with the requested contents."""

    secret_resolver = SecretResolver()

    def __init__(self, spec: dict[str, object]):
        super().__init__(spec)
        raw_path = spec.get("path")
        if not raw_path:
            raise ValueError("file operation requires a path")
        self.path = Path(str(raw_path))
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent", "directory"}:
            raise ValueError("file operation state must be 'present', 'absent', or 'directory'")
        raw_content = spec.get("content")
        self.content = "" if raw_content is None else str(raw_content)
        self.mode = self._parse_mode(spec.get("mode"))
        self.template = spec.get("template")
        self.variables = spec.get("variables", {})
        self.plan_dir = spec.get("_plan_dir")
        self.link_target = spec.get("link_target") or spec.get("target")
        self.owner_uid = self._parse_uid(spec.get("owner"))
        self.group_gid = self._parse_gid(spec.get("group"))
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
            return self._apply_symlink(host, executor)
        if self.state == "directory":
            changed, detail = executor.ensure_directory(self.path, mode=self.mode)
        elif self.state == "absent":
            removed = executor.remove_path(self.path)
            detail = "removed" if removed else "noop"
            changed = removed
        else:
            content = self._render_content(host)
            changed, detail = executor.write_file(self.path, content=content, mode=self.mode)
        changed, detail = self._apply_ownership(executor, changed, detail)
        return ActionResult(host=host.name, action="file", changed=changed, details=detail)

    def _render_content(self, host: HostConfig) -> str:
        if not self.template:
            return self.content
        template_path = Path(self.template).expanduser()
        if not template_path.is_absolute() and self.plan_dir is not None:
            template_path = self.plan_dir / template_path
        template_text = template_path.read_text()
        if self._looks_like_jinja(template_text):
            if jinja2 is None:
                raise RuntimeError("Jinja2 is required to render this template (pip install Jinja2)")
            return self._render_jinja(template_text, host)
        context: dict[str, object] = dict(host.variables)
        context.update(self.variables)
        context = self.secret_resolver.resolve(context)
        template = Template(template_text)
        return template.safe_substitute(context)

    def _apply_symlink(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.state == "absent":
            removed = executor.remove_path(self.path)
            detail = "removed" if removed else "noop"
            return ActionResult(host=host.name, action="file", changed=removed, details=detail)

        current_target = None
        try:
            if self.path.is_symlink():
                current_target = os.readlink(self.path)
        except OSError:
            current_target = None

        if current_target == self.link_target:
            return ActionResult(host=host.name, action="file", changed=False, details="noop")

        if not executor.dry_run:
            executor.remove_path(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(self.link_target, self.path)
        detail = f"link->{self.link_target}"
        return ActionResult(host=host.name, action="file", changed=True, details=detail)

    def _apply_ownership(self, executor: Executor, changed: bool, detail: str) -> tuple[bool, str]:
        if self.owner_uid is None and self.group_gid is None:
            return changed, detail
        chown_changed, chown_detail = executor.set_ownership(
            self.path, uid=self.owner_uid, gid=self.group_gid
        )
        if chown_changed:
            changed = True
            detail = f"{detail}, {chown_detail}" if detail and detail != "noop" else chown_detail
        return changed, detail

    @staticmethod
    def _parse_mode(value: Optional[object]) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        base = 8 if text.startswith("0") else 10
        return int(text, base)

    @staticmethod
    def _parse_uid(value: Optional[object]) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                return pwd.getpwnam(text).pw_uid
            except KeyError:
                raise ValueError(f"unknown user '{text}'")

    @staticmethod
    def _parse_gid(value: Optional[object]) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                return grp.getgrnam(text).gr_gid
            except KeyError:
                raise ValueError(f"unknown group '{text}'")

    def _render_jinja(self, template_text: str, host: HostConfig) -> str:
        assert jinja2 is not None  # For mypy/static checkers
        env = jinja2.Environment(undefined=jinja2.Undefined, autoescape=False)
        tmpl = env.from_string(template_text)
        context: dict[str, object] = dict(host.variables)
        context.update(self.variables)
        context = self.secret_resolver.resolve(context)
        return tmpl.render(**context)

    @staticmethod
    def _looks_like_jinja(template_text: str) -> bool:
        return bool(re.search(r"{[{%]", template_text))
