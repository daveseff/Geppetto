from pathlib import Path

from geppetto_automation.operations.yum_repo import YumRepoOperation
from geppetto_automation.executors import LocalExecutor
from geppetto_automation.types import HostConfig


def build_executor() -> LocalExecutor:
    host = HostConfig(name="local")
    return LocalExecutor(host, dry_run=False)


def test_yum_repo_present(tmp_path: Path) -> None:
    repo_path = tmp_path / "example.repo"
    spec = {
        "name": "example",
        "baseurl": "https://packages.example.com/repo",
        "gpgkey": "https://packages.example.com/RPM-GPG-KEY",
        "enabled": True,
        "gpgcheck": True,
        "metadata_expire": "6h",
        "options": {"priority": 10},
        "path": str(repo_path),
    }
    op = YumRepoOperation(spec)

    result = op.apply(HostConfig("local"), build_executor())
    assert result.changed is True
    text = repo_path.read_text()
    assert "baseurl=https://packages.example.com/repo" in text
    assert "gpgcheck=1" in text
    assert "priority=10" in text

    # Second run should be a noop
    result2 = op.apply(HostConfig("local"), build_executor())
    assert result2.changed is False
    assert "noop" in result2.details


def test_yum_repo_absent(tmp_path: Path) -> None:
    repo_path = tmp_path / "gone.repo"
    repo_path.write_text("placeholder")
    spec = {"name": "gone", "state": "absent", "path": str(repo_path)}
    op = YumRepoOperation(spec)

    result = op.apply(HostConfig("local"), build_executor())
    assert result.changed is True
    assert not repo_path.exists()
