from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
import pwd
import grp

from .base import Operation
from ..executors import CommandResult, Executor
from ..types import ActionResult, HostConfig


class GitPullOperation(Operation):
    """Clone or pull a git repository into a destination directory."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_source = spec.get("source") or spec.get("repo")
        if not raw_source:
            raise ValueError("git_pull requires a source repo")
        raw_dest = spec.get("dest") or spec.get("path")
        if not raw_dest:
            raise ValueError("git_pull requires a destination path")

        self.source = str(raw_source)
        self.dest = Path(str(raw_dest))
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("git_pull state must be 'present' or 'absent'")

        self.owner = spec.get("owner")
        self.group = spec.get("group")

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.state == "absent":
            removed = executor.remove_path(self.dest)
            detail = "removed" if removed else "noop"
            return ActionResult(host=host.name, action="git_pull", changed=removed, details=detail)

        changed = False
        reasons: list[str] = []

        if self.dest.exists():
            if not (self.dest / ".git").exists():
                raise ValueError(f"git_pull destination {self.dest} is not a git repository")
            if not executor.dry_run:
                before = self._git_rev(self.dest, executor)
                self._git_pull(self.dest, executor)
                after = self._git_rev(self.dest, executor)
                if before != after:
                    changed = True
                    reasons.append("pulled")
            else:
                self._git_pull(self.dest, executor)
        else:
            self._git_clone(self.source, self.dest, executor)
            changed = True
            reasons.append("cloned")

        if (self.owner is not None or self.group is not None) and self.dest.exists():
            owner_changed = self._apply_ownership(self.dest, executor)
            if owner_changed:
                changed = True
                reasons.append("ownership")

        detail = ", ".join(reasons) if reasons else "noop"
        return ActionResult(host=host.name, action="git_pull", changed=changed, details=detail)

    @staticmethod
    def _git_clone(source: str, dest: Path, executor: Executor) -> CommandResult:
        return executor.run(["git", "clone", source, str(dest)], mutable=True)

    @staticmethod
    def _git_pull(dest: Path, executor: Executor) -> CommandResult:
        result = executor.run(["git", "-C", str(dest), "pull", "--ff-only"], check=False, mutable=True)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "git pull failed"
            raise ValueError(message)
        return result

    @staticmethod
    def _git_rev(dest: Path, executor: Executor) -> str:
        result = executor.run(["git", "-C", str(dest), "rev-parse", "HEAD"], mutable=False)
        return result.stdout.strip()

    def _apply_ownership(self, dest: Path, executor: Executor) -> bool:
        uid = self._resolve_user(self.owner) if self.owner is not None else -1
        gid = self._resolve_group(self.group) if self.group is not None else -1
        changed = False

        for path in [dest, *self._walk_paths(dest)]:
            stat = path.lstat()
            if (uid != -1 and stat.st_uid != uid) or (gid != -1 and stat.st_gid != gid):
                changed = True
                if not executor.dry_run:
                    os.chown(path, uid, gid)
        return changed

    @staticmethod
    def _walk_paths(dest: Path) -> list[Path]:
        paths: list[Path] = []
        for root, dirs, files in os.walk(dest):
            for name in dirs:
                paths.append(Path(root) / name)
            for name in files:
                paths.append(Path(root) / name)
        return paths

    @staticmethod
    def _resolve_user(value: object) -> int:
        if isinstance(value, int):
            return value
        text = str(value)
        if text.isdigit():
            return int(text)
        return pwd.getpwnam(text).pw_uid

    @staticmethod
    def _resolve_group(value: object) -> int:
        if isinstance(value, int):
            return value
        text = str(value)
        if text.isdigit():
            return int(text)
        return grp.getgrnam(text).gr_gid
