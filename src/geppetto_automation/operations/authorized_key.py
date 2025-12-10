from __future__ import annotations

import base64
import os
import pwd
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


@dataclass
class UserRecord:
    home: Path
    uid: int
    gid: int


class AuthorizedKeyManager:
    def get_user(self, username: str) -> UserRecord:
        try:
            entry = pwd.getpwnam(username)
        except KeyError as exc:  # noqa: B904
            raise ValueError(f"User '{username}' does not exist") from exc
        return UserRecord(home=Path(entry.pw_dir), uid=entry.pw_uid, gid=entry.pw_gid)

    def read(self, path: Path) -> str:
        try:
            return path.read_text()
        except FileNotFoundError:
            return ""

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def chmod(self, path: Path, mode: int) -> None:
        os.chmod(path, mode)

    def chown(self, path: Path, uid: int, gid: int) -> None:
        os.chown(path, uid, gid)


class AuthorizedKeyOperation(Operation):
    """Ensure SSH authorized keys are present for a user."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_user = spec.get("user")
        if not raw_user:
            raise ValueError("authorized_key operation requires a user")
        self.user = str(raw_user)
        raw_key = spec.get("key")
        if not raw_key:
            raise ValueError("authorized_key operation requires a key")
        self.key = self._normalize_key(str(raw_key))
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("authorized_key state must be 'present' or 'absent'")
        self.manager = AuthorizedKeyManager()

    @staticmethod
    def _normalize_key(raw: str) -> str:
        text = raw.strip()
        if text.startswith("ssh-"):
            return text
        try:
            decoded = base64.b64decode(text, validate=True).decode().strip()
            if decoded:
                return decoded
        except Exception:
            pass
        return text

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        record = self.manager.get_user(self.user)
        ssh_dir = record.home / ".ssh"
        auth_file = ssh_dir / "authorized_keys"

        existing = self.manager.read(auth_file)
        keys = self._split_keys(existing)
        changed = False

        if self.state == "present":
            if self.key not in keys:
                keys.append(self.key)
                changed = True
        else:
            if self.key in keys:
                keys.remove(self.key)
                changed = True

        detail = "noop"
        if changed:
            detail = "added" if self.state == "present" else "removed"
            if not getattr(executor, "dry_run", False):
                new_content = "\n".join(keys) + ("\n" if keys else "")
                self.manager.write(auth_file, new_content)
                self.manager.chown(auth_file, record.uid, record.gid)
                self.manager.chmod(auth_file, 0o600)
                self.manager.chown(ssh_dir, record.uid, record.gid)
                self.manager.chmod(ssh_dir, 0o700)
        return ActionResult(host=host.name, action="authorized_key", changed=changed, details=detail)

    @staticmethod
    def _split_keys(content: str) -> list[str]:
        if not content:
            return []
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        seen: list[str] = []
        for line in lines:
            if line not in seen:
                seen.append(line)
        return seen
