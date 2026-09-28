import logging

from geppetto_automation import cli
from geppetto_automation.types import ActionResult


def test_format_result_failed(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    result = ActionResult(host="local", action="file", changed=False, details="boom", failed=True)
    line = cli.format_result(result)
    assert line.startswith("local::file failed - boom")


def test_format_result_success(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    result = ActionResult(host="local", action="package", changed=True, details="installed")
    line = cli.format_result(result)
    assert line.startswith("local::package changed - installed")


def test_log_result_suppresses_noop_at_info(caplog):
    result = ActionResult(
        host="bmg-staging",
        action="authorized_key",
        changed=False,
        details="noop",
        resource="Dave Seff",
    )

    caplog.set_level(logging.INFO, logger="geppetto")
    cli.log_result(result)

    assert not caplog.records


def test_log_result_emits_noop_at_debug(caplog):
    result = ActionResult(
        host="bmg-staging",
        action="authorized_key",
        changed=False,
        details="noop",
        resource="Dave Seff",
    )

    caplog.set_level(logging.DEBUG, logger="geppetto")
    cli.log_result(result)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG
    assert "changed=False details=noop" in caplog.records[0].message


def test_main_routes_import_without_loading_config(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "import_crontab",
        lambda user, host, task_name: f"{user}:{host}:{task_name}\n",
    )

    result = cli.main(["import", "cron", "alice", "--host", "web-1", "--task-name", "jobs"])

    assert result == 0
    assert capsys.readouterr().out == "alice:web-1:jobs\n"
