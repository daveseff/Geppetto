from forgeops_automation.operations.service import ServiceOperation
from forgeops_automation.types import HostConfig


class FakeSystemCtl:
    def __init__(self, enabled: bool = False, active: bool = False):
        self.enabled = enabled
        self.active = active
        self.available_called = False
        self.actions: list[str] = []

    def available(self) -> bool:
        self.available_called = True
        return True

    def is_enabled(self, executor, service: str) -> bool:  # noqa: ARG002
        return self.enabled

    def is_active(self, executor, service: str) -> bool:  # noqa: ARG002
        return self.active

    def enable(self, executor, service: str) -> None:  # noqa: ARG002
        self.enabled = True
        self.actions.append("enable")

    def disable(self, executor, service: str) -> None:  # noqa: ARG002
        self.enabled = False
        self.actions.append("disable")

    def start(self, executor, service: str) -> None:  # noqa: ARG002
        self.active = True
        self.actions.append("start")

    def stop(self, executor, service: str) -> None:  # noqa: ARG002
        self.active = False
        self.actions.append("stop")

    def restart(self, executor, service: str) -> None:  # noqa: ARG002
        self.actions.append("restart")


class DummyExecutor:
    def __init__(self):
        self.host = HostConfig(name="local")
        self.dry_run = False


def test_service_enable_and_start():
    op = ServiceOperation({"name": "sshd", "enabled": True, "state": "running"})
    fake = FakeSystemCtl(enabled=False, active=False)
    op.systemctl = fake
    result = op.apply(HostConfig("local"), DummyExecutor())

    assert result.changed is True
    assert "enabled" in result.details
    assert "started" in result.details
    assert fake.actions == ["enable", "start"]


def test_service_restart_only():
    op = ServiceOperation({"name": "cron", "restart": True})
    fake = FakeSystemCtl(enabled=True, active=True)
    op.systemctl = fake
    result = op.apply(HostConfig("local"), DummyExecutor())

    assert result.changed is True
    assert result.details == "restarted"
    assert fake.actions == ["restart"]


def test_service_no_changes_returns_noop():
    op = ServiceOperation({"name": "sshd", "enabled": True, "state": "running"})
    fake = FakeSystemCtl(enabled=True, active=True)
    op.systemctl = fake
    result = op.apply(HostConfig("local"), DummyExecutor())

    assert result.changed is False
    assert result.details == "noop"
