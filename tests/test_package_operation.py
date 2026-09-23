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


class VersionedPackageManager(FakePackageManager):
    def __init__(self, versions, *, no_upgrade=False, fail=False):
        super().__init__(set(versions))
        self.versions = dict(versions)
        self.upgraded_calls = []
        self.no_upgrade = no_upgrade
        self.fail = fail

    def has_update(self, executor, package):
        return self.versions[package] != "2"

    def installed_version(self, executor, package):
        return self.versions[package]

    def install(self, executor, packages):
        if not executor.dry_run:
            super().install(executor, packages)
            self.versions.update(dict.fromkeys(packages, "2"))

    def upgrade(self, executor, packages):
        self.upgraded_calls.append(packages)
        if self.fail:
            raise RuntimeError("upgrade failed")
        if not executor.dry_run and not self.no_upgrade:
            self.versions.update(dict.fromkeys(packages, "2"))


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("versions,changed", [({}, True), ({"git": "1"}, True), ({"git": "2"}, False)])
def test_latest_install_upgrade_and_noop(monkeypatch, dry_run, versions, changed):
    manager = VersionedPackageManager(versions)
    monkeypatch.setattr(pkg.PackageManagerFactory, "create", lambda _: manager)
    host = HostConfig("local")
    result = pkg.PackageOperation({"name": "git", "state": "latest"}).apply(
        host, LocalExecutor(host, dry_run=dry_run)
    )
    assert result.changed is changed
    assert manager.versions == (versions if dry_run else {"git": "2"})


def test_latest_mixed_packages_and_duplicates():
    manager = VersionedPackageManager({"git": "1", "jq": "2"})
    changed, details = manager.ensure_latest(build_executor(), ["git", "jq", "htop", "git"])
    assert changed
    assert details == "installed=htop upgraded=git"
    assert manager.installed_calls == [["htop"]]
    assert manager.upgraded_calls == [["git"]]


@pytest.mark.parametrize(
    "versions,no_upgrade,fail,changed,children,failed",
    [
        ({}, False, False, True, 1, False),
        ({"git": "1"}, False, False, True, 1, False),
        ({"git": "2"}, False, False, False, 0, False),
        ({"git": "1"}, True, False, False, 0, False),
        ({"git": "1"}, False, True, False, 0, True),
    ],
)
def test_latest_dsl_on_success(monkeypatch, versions, no_upgrade, fail, changed, children, failed):
    from geppetto_automation.dsl import DSLParser
    from geppetto_automation import runner as runner_mod
    from geppetto_automation.runner import TaskRunner
    from geppetto_automation.types import ActionResult

    manager = VersionedPackageManager(versions, no_upgrade=no_upgrade, fail=fail)
    monkeypatch.setattr(pkg.PackageManagerFactory, "create", lambda _: manager)

    class Child:
        def __init__(self, spec):
            pass

        def apply(self, host, executor):
            return ActionResult(host=host.name, action="exec", changed=True, details="ran")

    monkeypatch.setitem(runner_mod.OPERATION_REGISTRY, "exec", Child)
    plan = DSLParser().parse_text("""
    node 'local' { connection => local }
    task 'packages' on ['local'] {
      package { 'git':
        ensure => latest
        on_success => {
          exec { 'after-upgrade': command => 'ignored' }
        }
      }
    }
    """)
    results = TaskRunner(plan).run()
    assert results[0].changed is changed
    assert results[0].failed is failed
    assert len(results) == 1 + children


class QueryExecutor:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def run(self, command, **kwargs):
        from geppetto_automation.executors import CommandResult

        self.calls.append((command, kwargs))
        return CommandResult(list(command), self.stdout, self.stderr, self.returncode)


@pytest.mark.parametrize("manager,command,stdout,code,expected", [
    (pkg.AptPackageManager, ["apt-get", "--simulate", "install", "git"], "Inst git [1] (2 repo)\n", 0, True),
    (pkg.AptPackageManager, ["apt-get", "--simulate", "install", "git"], "Inst dependency [1] (2 repo)\n", 0, False),
    (pkg.AptPackageManager, ["apt-get", "--simulate", "install", "git"], "Inst git:amd64 [1] (2 repo)\n", 0, True),
    (pkg.DnfPackageManager, ["dnf", "check-update", "git"], "", 100, True),
    (pkg.DnfPackageManager, ["dnf", "check-update", "git"], "", 0, False),
    (pkg.YumPackageManager, ["yum", "check-update", "git"], "", 100, True),
    (pkg.YumPackageManager, ["yum", "check-update", "git"], "", 0, False),
    (pkg.BrewPackageManager, ["brew", "outdated", "--quiet", "git"], "git\n", 1, True),
    (pkg.BrewPackageManager, ["brew", "outdated", "--quiet", "git"], "", 0, False),
    (pkg.PacmanPackageManager, ["pacman", "-Qu", "git"], "git 1 -> 2\n", 0, True),
    (pkg.PacmanPackageManager, ["pacman", "-Qu", "git"], "", 1, False),
])
def test_provider_update_queries(manager, command, stdout, code, expected):
    executor = QueryExecutor(stdout, code)
    assert manager().has_update(executor, "git") is expected
    assert executor.calls == [(command, {"check": False, "mutable": False, "env": {"LC_ALL": "C"}})]


@pytest.mark.parametrize("manager", [
    pkg.AptPackageManager, pkg.DnfPackageManager, pkg.YumPackageManager,
    pkg.BrewPackageManager, pkg.PacmanPackageManager,
])
def test_update_query_failure_is_not_noop(manager):
    import subprocess

    with pytest.raises(subprocess.CalledProcessError):
        manager().has_update(QueryExecutor(returncode=2, stderr="query failed"), "git")


@pytest.mark.parametrize("manager,command", [
    (pkg.AptPackageManager, ["apt-get", "install", "-y", "git"]),
    (pkg.DnfPackageManager, ["dnf", "upgrade", "-y", "git"]),
    (pkg.YumPackageManager, ["yum", "upgrade", "-y", "git"]),
    (pkg.BrewPackageManager, ["brew", "upgrade", "git"]),
    (pkg.PacmanPackageManager, ["pacman", "-S", "--noconfirm", "git"]),
])
def test_provider_upgrade_commands(manager, command):
    executor = QueryExecutor()
    manager().upgrade(executor, ["git"])
    assert executor.calls == [(command, {})]


@pytest.mark.parametrize("manager", [
    pkg.AptPackageManager, pkg.DnfPackageManager, pkg.YumPackageManager,
    pkg.BrewPackageManager, pkg.PacmanPackageManager,
])
def test_dry_run_never_executes_upgrade(monkeypatch, manager):
    def unexpected(*args, **kwargs):
        pytest.fail("dry-run executed a mutable command")

    monkeypatch.setattr("subprocess.run", unexpected)
    manager().upgrade(LocalExecutor(HostConfig("local"), dry_run=True), ["git"])


@pytest.mark.parametrize("manager", [pkg.BrewPackageManager, pkg.PacmanPackageManager])
def test_ambiguous_query_exit_with_error_is_failure(manager):
    import subprocess

    with pytest.raises(subprocess.CalledProcessError):
        manager().has_update(QueryExecutor(returncode=1, stderr="database unavailable"), "git")


@pytest.mark.parametrize("manager,command", [
    (pkg.AptPackageManager, ["dpkg-query", "-W", "-f", "${Version}", "git"]),
    (pkg.DnfPackageManager, ["rpm", "-q", "--qf", "%{NAME} %{ARCH} %{EPOCHNUM}:%{VERSION}-%{RELEASE}\n", "git"]),
    (pkg.YumPackageManager, ["rpm", "-q", "--qf", "%{NAME} %{ARCH} %{EPOCHNUM}:%{VERSION}-%{RELEASE}\n", "git"]),
    (pkg.BrewPackageManager, ["brew", "list", "--versions", "git"]),
    (pkg.PacmanPackageManager, ["pacman", "-Q", "git"]),
])
def test_provider_version_queries(manager, command):
    executor = QueryExecutor("2\n")
    assert manager().installed_version(executor, "git") == "2"
    assert executor.calls[0][0] == command
    assert executor.calls[0][1]["mutable"] is False
