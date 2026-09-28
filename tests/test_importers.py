import subprocess

import pytest

from geppetto_automation.dsl import DSLParser
from geppetto_automation.importers import import_crontab


def test_import_crontab_renders_one_resource_per_job(monkeypatch) -> None:
    content = (
        "# nightly\n"
        "MAILTO=''\n"
        "0 5 * * * /usr/sbin/aide --check\n"
        "0 2 * * 3,5 /usr/local/bin/copy_snapshot first\n"
        "0 2 * * 3,5 /usr/local/bin/copy_snapshot second\n"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, content, ""),
    )

    rendered = import_crontab("alice", host="server-1")
    plan = DSLParser().parse_text(rendered)
    actions = plan.tasks[0].actions

    assert plan.tasks[0].hosts == ["server-1"]
    assert [action.data["name"] for action in actions] == [
        "alice-aide",
        "alice-copy-snapshot",
        "alice-copy-snapshot-2",
    ]
    assert all(action.type == "cron" for action in actions)
    assert all(action.data["target"] == "crontab_entry" for action in actions)
    assert actions[0].data["minute"] == "0"
    assert actions[0].data["command"] == "/usr/sbin/aide --check"
    assert actions[1].data["weekday"] == "3,5"
    assert actions[0].data["env"] == {"MAILTO": "''"}


def test_import_crontab_detects_hostname_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "@daily /bin/backup\n", ""),
    )
    monkeypatch.setattr("geppetto_automation.importers.socket.gethostname", lambda: "web-2")

    plan = DSLParser().parse_text(import_crontab("root"))

    assert plan.tasks[0].hosts == ["web-2"]
    assert plan.tasks[0].actions[0].data["special"] == "@daily"


def test_import_crontab_reports_read_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "no crontab for missing"),
    )

    with pytest.raises(RuntimeError, match="no crontab for missing"):
        import_crontab("missing")
