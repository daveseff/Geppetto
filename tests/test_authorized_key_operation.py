from pathlib import Path

import os

from geppetto_automation.operations.authorized_key import (
    AuthorizedKeyManager,
    AuthorizedKeyOperation,
    UserRecord,
)
from geppetto_automation.types import HostConfig


class FakeManager(AuthorizedKeyManager):
    def __init__(self, home: Path):
        self.record = UserRecord(home=home, uid=1000, gid=1000)
        self.contents: dict[Path, str] = {}
        self.chmod_calls: list[tuple[Path, int]] = []
        self.chown_calls: list[tuple[Path, int, int]] = []

    def get_user(self, username: str):  # type: ignore[override]
        return self.record

    def read(self, path: Path) -> str:  # type: ignore[override]
        return self.contents.get(path, "")

    def write(self, path: Path, content: str) -> None:  # type: ignore[override]
        self.contents[path] = content

    def chmod(self, path: Path, mode: int) -> None:  # type: ignore[override]
        self.chmod_calls.append((path, mode))

    def chown(self, path: Path, uid: int, gid: int) -> None:  # type: ignore[override]
        self.chown_calls.append((path, uid, gid))


def executor_stub():
    class Stub:
        dry_run = False

    return Stub()


def test_adds_missing_key(tmp_path: Path):
    op = AuthorizedKeyOperation({"user": "deploy", "key": "ssh-rsa AAA"})
    manager = FakeManager(tmp_path)
    op.manager = manager

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    auth_file = manager.record.home / ".ssh" / "authorized_keys"
    assert manager.contents[auth_file] == "ssh-rsa AAA\n"


def test_removes_existing_key(tmp_path: Path):
    home = tmp_path
    manager = FakeManager(home)
    auth_file = home / ".ssh" / "authorized_keys"
    manager.contents[auth_file] = "ssh-rsa AAA\nssh-ed25519 BBB\n"

    op = AuthorizedKeyOperation({"user": "deploy", "key": "ssh-ed25519 BBB", "state": "absent"})
    op.manager = manager

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert manager.contents[auth_file] == "ssh-rsa AAA\n"
