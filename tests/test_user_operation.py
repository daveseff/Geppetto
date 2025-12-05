from forgeops_automation.operations.user import UserInfo, UserManager, UserOperation
from forgeops_automation.types import HostConfig


class FakeManager(UserManager):
    def __init__(self, existing: UserInfo | None = None, locked: bool = False):
        self._info = existing
        self.locked = locked
        self.actions: list[tuple[str, tuple]] = []

    def get(self, username: str):  # type: ignore[override]
        return self._info

    def add(self, executor, name, *, shell, system, create_home, comment):  # type: ignore[override]
        self.actions.append(("add", (name, shell, system, create_home, comment)))
        self._info = UserInfo(name=name, shell=shell or "/bin/bash", home=f"/home/{name}")

    def delete(self, executor, name, *, remove_home):  # type: ignore[override]
        self.actions.append(("delete", (name, remove_home)))
        self._info = None

    def set_shell(self, executor, name, shell):  # type: ignore[override]
        self.actions.append(("shell", (name, shell)))
        if self._info:
            self._info = UserInfo(name=name, shell=shell, home=self._info.home)

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
    assert ("add", ("svc", "/bin/bash", False, True, None)) in fake.actions
    assert ("lock", ("svc",)) in fake.actions


def test_updates_shell_and_unlocks():
    existing = UserInfo(name="svc", shell="/bin/sh", home="/home/svc")
    op = UserOperation({"name": "svc", "shell": "/bin/bash", "locked": False})
    fake = FakeManager(existing=existing, locked=True)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert "shell" in result.details
    assert "unlocked" in result.details


def test_removes_user():
    existing = UserInfo(name="svc", shell="/bin/sh", home="/home/svc")
    op = UserOperation({"name": "svc", "state": "absent", "remove_home": True})
    fake = FakeManager(existing=existing, locked=False)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert result.details == "removed"
    assert ("delete", ("svc", True)) in fake.actions
