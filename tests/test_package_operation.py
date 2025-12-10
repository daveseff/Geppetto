import pytest

from geppetto_automation.executors import LocalExecutor
from geppetto_automation.operations import package as pkg
from geppetto_automation.operations.package import PackageManager
from geppetto_automation.types import HostConfig


class FakePackageManager(PackageManager):
    name = "fake"

    def __init__(self, installed: set[str]):
        self._installed = installed
        self.installed_calls: list[list[str]] = []
        self.removed_calls: list[list[str]] = []

    def install(self, executor, packages: list[str]) -> None:  # type: ignore[override]
        self.installed_calls.append(packages)
        self._installed.update(packages)

    def remove(self, executor, packages: list[str]) -> None:  # type: ignore[override]
        self.removed_calls.append(packages)
        for pkg_name in packages:
            self._installed.discard(pkg_name)

    def is_installed(self, executor, package: str) -> bool:  # type: ignore[override]
        return package in self._installed


@pytest.fixture
def fake_manager(monkeypatch):
    installed = {"git"}

    def create(cls, preferred):
        return FakePackageManager(installed)

    monkeypatch.setattr(pkg.PackageManagerFactory, "create", classmethod(create))
    return installed


def build_executor() -> LocalExecutor:
    host = HostConfig(name="local")
    return LocalExecutor(host, dry_run=False)


def test_package_present_installs_missing(fake_manager):
    spec = {"packages": ["git", "htop"], "state": "present"}
    op = pkg.PackageOperation(spec)
    result = op.apply(HostConfig("local"), build_executor())

    assert result.changed is True
    assert "htop" in fake_manager


def test_package_absent_removes_installed(fake_manager):
    spec = {"packages": ["git"], "state": "absent"}
    op = pkg.PackageOperation(spec)
    result = op.apply(HostConfig("local"), build_executor())

    assert result.changed is True
    assert "git" not in fake_manager


def test_package_requires_names():
    with pytest.raises(ValueError):
        pkg.PackageOperation({})
