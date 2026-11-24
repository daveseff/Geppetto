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


def test_managed_key_is_idempotent_and_repairs_only_its_duplicates(tmp_path):
    manager = FakeManager(tmp_path)
    path = tmp_path / '.ssh' / 'authorized_keys'
    manager.contents[path] = '# keep comment\nssh-rsa AAA first\nssh-ed25519 BBB second\nssh-rsa AAA first\nssh-ed25519 BBB second\nrestrict ssh-rsa AAA restricted\n'
    op = AuthorizedKeyOperation({'user': 'ansible', 'key': 'ssh-rsa AAA first'})
    op.manager = manager
    assert op.apply(HostConfig('local'), executor_stub()).changed
    expected = '# keep comment\nssh-rsa AAA first\nssh-ed25519 BBB second\nssh-ed25519 BBB second\nrestrict ssh-rsa AAA restricted\n'
    assert manager.contents[path] == expected
    assert not op.apply(HostConfig('local'), executor_stub()).changed
    op.state = 'absent'
    assert op.apply(HostConfig('local'), executor_stub()).changed
    assert manager.contents[path] == '# keep comment\nssh-ed25519 BBB second\nssh-ed25519 BBB second\nrestrict ssh-rsa AAA restricted\n'


def test_duplicate_repair_dry_run(tmp_path):
    manager = FakeManager(tmp_path)
    path = tmp_path / '.ssh' / 'authorized_keys'
    original = 'ssh-rsa AAA\nssh-rsa AAA\nssh-ed25519 BBB\n'
    manager.contents[path] = original
    op = AuthorizedKeyOperation({'user': 'ansible', 'key': 'ssh-rsa AAA'})
    op.manager = manager
    executor = executor_stub()
    executor.dry_run = True
    assert op.apply(HostConfig('local'), executor).changed
    assert manager.contents[path] == original



def test_rejects_multiple_keys_in_one_resource():
    import base64
    import pytest
    bundle = 'ssh-rsa AAA first\nssh-ed25519 BBB second'
    for value in (bundle, base64.b64encode(bundle.encode()).decode(),
                  'ssh-rsa AAA\nssh-rsa AAA', ['ssh-rsa AAA', 'ssh-ed25519 BBB']):
        with pytest.raises(ValueError, match='separate authorized_key resource'):
            AuthorizedKeyOperation({'user': 'ansible', 'name': 'ansible', 'key': value})


def test_accepts_single_key_with_options_comment_and_surrounding_whitespace():
    import base64
    key = 'restrict ssh-ed25519 AAA management key'
    for value in ('\n' + key + '\n', base64.b64encode(key.encode()).decode()):
        assert AuthorizedKeyOperation({'user': 'ansible', 'key': value}).key == key
