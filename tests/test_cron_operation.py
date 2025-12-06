from pathlib import Path

from forgeops_automation.executors import LocalExecutor
from forgeops_automation.operations.cron import CronOperation
from forgeops_automation.types import HostConfig


def test_cron_writes_file(tmp_path: Path) -> None:
    cron_dir = tmp_path / "cron.d"
    spec = {
        "name": "rotate-logs",
        "user": "root",
        "minute": "0",
        "hour": "*/6",
        "command": "/usr/local/bin/rotate",
        "env": {"MAILTO": ""},
        "cron_dir": str(cron_dir),
    }
    op = CronOperation(spec)
    executor = LocalExecutor(HostConfig(name="local"), dry_run=False)

    result = op.apply(HostConfig("local"), executor)
    assert result.changed is True
    cron_file = cron_dir / "rotate-logs.cron"
    assert cron_file.exists()
    assert "MAILTO=" in cron_file.read_text()

    result = op.apply(HostConfig("local"), executor)
    assert result.changed is False


def test_cron_absent(tmp_path: Path) -> None:
    cron_file = tmp_path / "cron.d" / "job.cron"
    cron_file.parent.mkdir(parents=True)
    cron_file.write_text("*")
    spec = {"name": "job", "command": "/bin/true", "state": "absent", "cron_dir": str(tmp_path / "cron.d")}
    op = CronOperation(spec)
    executor = LocalExecutor(HostConfig(name="local"), dry_run=False)

    result = op.apply(HostConfig("local"), executor)
    assert result.changed is True
    assert not cron_file.exists()
