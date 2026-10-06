from pathlib import Path
import subprocess

from geppetto_automation.executors import CommandResult, LocalExecutor
from geppetto_automation.operations.cron import CronOperation
from geppetto_automation.types import HostConfig


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


class CrontabExecutor(LocalExecutor):
    def __init__(self, content: str | None):
        super().__init__(HostConfig(name="local"), dry_run=False)
        self.content = content
        self.installed: list[str] = []

    def run(self, command, **kwargs):
        if command[-1] == "-l":
            if self.content is None:
                return CommandResult(list(command), "", "no crontab for alice", 1)
            return CommandResult(list(command), self.content, "", 0)
        if command[-1] == "-":
            self.content = kwargs["input_text"]
            self.installed.append(self.content)
        elif command[-1] == "-r":
            self.content = None
        return CommandResult(list(command), "", "", 0)


def test_imported_crontab_is_adopted_without_change() -> None:
    content = "MAILTO=''\n0 2 * * * /usr/local/bin/backup\n"
    executor = CrontabExecutor(content)
    op = CronOperation(
        {"name": "alice-crontab", "target": "crontab", "user": "alice", "content": content}
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is False
    assert result.details == "noop"
    assert executor.installed == []


def test_managed_crontab_is_replaced_as_one_resource() -> None:
    executor = CrontabExecutor("0 2 * * * /old\n")
    op = CronOperation(
        {"name": "alice-crontab", "target": "crontab", "user": "alice", "content": "@daily /new"}
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert executor.installed == ["@daily /new\n"]


def test_imported_crontab_entry_is_adopted_without_change() -> None:
    executor = CrontabExecutor("0 5 * * * /usr/sbin/aide --check\n")
    op = CronOperation(
        {
            "name": "root-aide",
            "target": "crontab_entry",
            "user": "root",
            "minute": "0",
            "hour": "5",
            "command": "/usr/sbin/aide --check",
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is False
    assert executor.installed == []


def test_crontab_entry_absent_removes_only_matching_job() -> None:
    executor = CrontabExecutor("0 5 * * * /usr/sbin/aide --check\n@daily /bin/backup\n")
    op = CronOperation(
        {
            "name": "root-aide",
            "target": "crontab_entry",
            "user": "root",
            "minute": "0",
            "hour": "5",
            "command": "/usr/sbin/aide --check",
            "state": "absent",
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert executor.installed == ["@daily /bin/backup\n"]


def test_crontab_entry_schedule_change_updates_existing_job() -> None:
    executor = CrontabExecutor(
        "0 5 * * * /usr/sbin/aide --check\n"
        "0 1 * * 3,5 /usr/local/bin/share_snapshot billing-centre-prd\n"
    )
    op = CronOperation(
        {
            "name": "billing-centre-share-snapshot",
            "target": "crontab_entry",
            "user": "root",
            "minute": "0",
            "hour": "1",
            "weekday": "1-5",
            "command": "/usr/local/bin/share_snapshot billing-centre-prd",
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert result.details == "updated"
    assert executor.installed == [
        "0 5 * * * /usr/sbin/aide --check\n"
        "0 1 * * 1-5 /usr/local/bin/share_snapshot billing-centre-prd\n"
    ]


def test_crontab_entry_reconciles_duplicate_schedules() -> None:
    command = "/usr/local/bin/share_snapshot billing-centre-prd"
    executor = CrontabExecutor(
        f"0 1 * * 3,5 {command}\n"
        f"0 1 * * 1-5 {command}\n"
    )
    op = CronOperation(
        {
            "name": "billing-centre-share-snapshot",
            "target": "crontab_entry",
            "minute": "0",
            "hour": "1",
            "weekday": "1-5",
            "command": command,
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert executor.installed == [f"0 1 * * 1-5 {command}\n"]


def test_crontab_entry_absent_matches_command_after_schedule_change() -> None:
    executor = CrontabExecutor("0 1 * * 3,5 /bin/backup\n@daily /bin/report\n")
    op = CronOperation(
        {
            "name": "backup",
            "target": "crontab_entry",
            "command": "/bin/backup",
            "state": "absent",
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert executor.installed == ["@daily /bin/report\n"]


def test_dry_run_crontab_entries_see_prior_planned_writes(monkeypatch) -> None:
    monkeypatch.setattr(
        "geppetto_automation.executors.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, "", "no crontab for root"
        ),
    )
    executor = LocalExecutor(HostConfig(name="local"), dry_run=True)
    first = CronOperation(
        {"name": "first", "target": "crontab_entry", "command": "/bin/first"}
    )
    second = CronOperation(
        {"name": "second", "target": "crontab_entry", "command": "/bin/second"}
    )

    first_result = first.apply(HostConfig("local"), executor)
    second_result = second.apply(HostConfig("local"), executor)

    assert first_result.details == "created"
    assert second_result.details == "updated"
