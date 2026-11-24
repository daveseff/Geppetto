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


def test_reconcile_refreshes_stale_config_before_validation(tmp_path, monkeypatch, capsys):
    plan = tmp_path / 'plan.fops'
    header = "node 'local' { connection => local }\ntask 'keys' on 'local' { "
    plan.write_text(header + "authorized_key { 'ansible': user => 'ansible' key => 'ssh-rsa AAA\nssh-ed25519 BBB' } }")
    config = tmp_path / 'main.conf'
    config.write_text('[defaults]\n')
    state = tmp_path / 'state.json'
    events = []
    def refresh(cfg):
        events.append('refresh')
        plan.write_text("node 'local' { connection => local }\n")
    monkeypatch.setattr(cli, '_sync_config_service', refresh)
    monkeypatch.setattr(cli, '_sync_config_repo', lambda cfg: events.append('repo'))
    def forbidden(*args):
        raise AssertionError('must never apply resources')
    monkeypatch.setattr(cli.TaskRunner, 'run', forbidden)
    args = [str(plan), '--config', str(config), '--state-file', str(state), '--reconcile-state', '--dry-run']
    assert cli.main(args) == 1
    assert events == []
    assert '--refresh-config' in capsys.readouterr().err
    assert cli.main(args + ['--refresh-config']) == 0
    assert events == ['refresh', 'repo']
    assert not state.exists()
    assert not list(tmp_path.glob('*.bak'))


def test_refresh_and_skip_sync_are_mutually_exclusive():
    import pytest
    with pytest.raises(SystemExit):
        cli.parse_args(['--refresh-config', '--skip-sync'])


def test_reconcile_refresh_failure_does_not_load_or_reconcile(tmp_path, monkeypatch):
    config = tmp_path / 'main.conf'
    config.write_text('[defaults]\n')
    def fail(cfg):
        raise RuntimeError('config server unavailable')
    def forbidden(*args, **kwargs):
        raise AssertionError('must stop after refresh failure')
    monkeypatch.setattr(cli, '_sync_config_service', fail)
    monkeypatch.setattr(cli.InventoryLoader, 'load', forbidden)
    monkeypatch.setattr(cli, 'reconcile_state', forbidden)
    assert cli.main(['--config', str(config), '--reconcile-state', '--dry-run', '--refresh-config']) == 1


def test_target_cli_applies_only_selected_file(tmp_path, monkeypatch, capsys):
    from geppetto_automation import cli
    one, two = tmp_path / 'one', tmp_path / 'two'
    plan = tmp_path / 'plan.fops'
    plan.write_text("node 'local' { connection => local }\ntask 'files' on 'local' {\n" +
                    ''.join("file { '" + str(path) + "': content => 'new' }\n" for path in (one, two)) + '}')
    config = tmp_path / 'main.conf'
    config.write_text('[defaults]\nlog_file = "' + str(tmp_path / 'log') + '"\n')
    state = tmp_path / 'state.json'
    args = [str(plan), '--config', str(config), '--state-file', str(state), '--skip-sync', '--target', f'file.{one}']
    assert cli.main(args + ['--dry-run']) == 0
    assert not one.exists() and not two.exists() and not state.exists()
    assert 'target=local::file.' in capsys.readouterr().out
    assert cli.main(args) == 0
    assert one.read_text() == 'new'
    assert not two.exists()


def test_target_cannot_be_used_with_reconciliation():
    import pytest
    with pytest.raises(SystemExit):
        cli.parse_args(['--target', 'user.ansible', '--reconcile-state'])
