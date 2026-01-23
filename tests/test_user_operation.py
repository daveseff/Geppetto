from geppetto_automation.operations.user import UserInfo, UserManager, UserOperation
from geppetto_automation.types import HostConfig


class FakeManager(UserManager):
    def __init__(self, existing: UserInfo | None = None, locked: bool = False):
        self._info = existing
        self.locked = locked
        self.actions: list[tuple[str, tuple]] = []

    def get(self, username: str):  # type: ignore[override]
        return self._info

    def add(self, executor, name, *, shell, system, create_home, comment, uid, gid):  # type: ignore[override]
        self.actions.append(("add", (name, shell, system, create_home, comment, uid, gid)))
        self._info = UserInfo(
            name=name,
            shell=shell or "/bin/bash",
            home=f"/home/{name}",
            uid=uid or 1000,
            gid=gid or 1000,
        )

    def delete(self, executor, name, *, remove_home):  # type: ignore[override]
        self.actions.append(("delete", (name, remove_home)))
        self._info = None

    def set_shell(self, executor, name, shell):  # type: ignore[override]
        self.actions.append(("shell", (name, shell)))
        if self._info:
            self._info = UserInfo(
                name=name,
                shell=shell,
                home=self._info.home,
                uid=self._info.uid,
                gid=self._info.gid,
            )

    def set_uid_gid(self, executor, name, *, uid, gid):  # type: ignore[override]
        self.actions.append(("uid_gid", (name, uid, gid)))
        if self._info:
            self._info = UserInfo(
                name=name,
                shell=self._info.shell,
                home=self._info.home,
                uid=uid if uid is not None else self._info.uid,
                gid=gid if gid is not None else self._info.gid,
            )

    def lock(self, executor, name):  # type: ignore[override]
        self.actions.append(("lock", (name,)))
        self.locked = True

    def unlock(self, executor, name):  # type: ignore[override]
        self.actions.append(("unlock", (name,)))
        self.locked = False

    def is_locked(self, executor, name):  # type: ignore[override]
        return self.locked


def executor_stub():
    class Stub:
        dry_run = False

        def run(self, command, *, check=True, mutable=True):  # noqa: ARG002
            class Result:
                def __init__(self):
                    self.returncode = 0
                    self.stdout = ""
                    self.stderr = ""

            return Result()

    return Stub()


def test_creates_user_when_missing(monkeypatch):
    op = UserOperation({"name": "svc", "shell": "/bin/bash", "locked": True})
    fake = FakeManager(existing=None, locked=False)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert "created" in result.details
    assert ("add", ("svc", "/bin/bash", False, True, None, None, None)) in fake.actions
    assert ("lock", ("svc",)) in fake.actions


def test_updates_shell_and_unlocks():
    existing = UserInfo(name="svc", shell="/bin/sh", home="/home/svc", uid=1000, gid=1000)
    op = UserOperation({"name": "svc", "shell": "/bin/bash", "locked": False})
    fake = FakeManager(existing=existing, locked=True)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert "shell" in result.details
    assert "unlocked" in result.details


def test_removes_user():
    existing = UserInfo(name="svc", shell="/bin/sh", home="/home/svc", uid=1000, gid=1000)
    op = UserOperation({"name": "svc", "state": "absent", "remove_home": True})
    fake = FakeManager(existing=existing, locked=False)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert result.details == "removed"
    assert ("delete", ("svc", True)) in fake.actions


def test_updates_uid_gid():
    existing = UserInfo(name="svc", shell="/bin/sh", home="/home/svc", uid=1000, gid=1000)
    op = UserOperation({"name": "svc", "uid": 2000, "gid": 3000})
    fake = FakeManager(existing=existing, locked=False)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert "uid" in result.details
    assert "gid" in result.details
    assert ("uid_gid", ("svc", 2000, 3000)) in fake.actions
