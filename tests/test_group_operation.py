from geppetto_automation.operations.group import GroupInfo, GroupManager, GroupOperation
from geppetto_automation.types import HostConfig


class FakeManager(GroupManager):
    def __init__(self, existing: GroupInfo | None = None):
        self._info = existing
        self.actions: list[tuple[str, tuple]] = []

    def get(self, name: str):  # type: ignore[override]
        return self._info

    def add(self, executor, name, *, gid):  # type: ignore[override]
        self.actions.append(("add", (name, gid)))
        self._info = GroupInfo(name=name, gid=gid or 1000)

    def delete(self, executor, name):  # type: ignore[override]
        self.actions.append(("delete", (name,)))
        self._info = None

    def set_gid(self, executor, name, gid):  # type: ignore[override]
        self.actions.append(("gid", (name, gid)))
        if self._info:
            self._info = GroupInfo(name=name, gid=gid)


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


def test_creates_group_with_gid():
    op = GroupOperation({"name": "svc", "gid": 2000})
    fake = FakeManager(existing=None)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert "created" in result.details
    assert ("add", ("svc", 2000)) in fake.actions


def test_updates_gid_when_different():
    existing = GroupInfo(name="svc", gid=1000)
    op = GroupOperation({"name": "svc", "gid": 2000})
    fake = FakeManager(existing=existing)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert "gid" in result.details
    assert ("gid", ("svc", 2000)) in fake.actions


def test_removes_group():
    existing = GroupInfo(name="svc", gid=1000)
    op = GroupOperation({"name": "svc", "state": "absent"})
    fake = FakeManager(existing=existing)
    op.manager = fake

    result = op.apply(HostConfig("local"), executor_stub())

    assert result.changed is True
    assert result.details == "removed"
    assert ("delete", ("svc",)) in fake.actions
