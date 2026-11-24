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


def test_main_routes_all_user_crontab_import(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "import_all_crontabs",
        lambda host, task_name: f"all:{host}:{task_name}\n",
    )

    result = cli.main(["import", "cron", "--all-users"])

    assert result == 0
    assert capsys.readouterr().out == "all:None:None\n"


def test_reconcile_cli_does_not_sync_log_or_apply(tmp_path, monkeypatch, capsys):
    target = tmp_path / 'managed'
    target.write_text('live')
    plan = tmp_path / 'plan.fops'
    plan.write_text("node 'local' { connection => local }\ntask 'demo' on 'local' { file { '" + str(target) + "': content => 'desired' } }")
    config = tmp_path / 'main.conf'
    config.write_text('[defaults]\nlog_file = "' + str(tmp_path / 'log') + '"\n')
    def forbidden(*args):
        raise AssertionError('reconciliation must not sync or apply')
    monkeypatch.setattr(cli, '_sync_config_service', forbidden)
    monkeypatch.setattr(cli, '_sync_config_repo', forbidden)
    monkeypatch.setattr(cli.TaskRunner, 'run', forbidden)
    path = tmp_path / 'state.json'
    assert cli.main([str(plan), '--config', str(config), '--state-file', str(path), '--reconcile-state', '--dry-run']) == 0
    assert 'live: tracked' in capsys.readouterr().out
    assert not path.exists()
    assert not (tmp_path / 'log').exists()
    assert target.read_text() == 'live'
