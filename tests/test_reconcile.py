import json
from pathlib import Path

import pytest

from geppetto_automation.reconcile import reconcile_state
from geppetto_automation.state import StateStore
from geppetto_automation.types import ActionSpec, HostConfig, Plan, TaskSpec


def test_reconcile_probes_live_files_including_hooks_without_applying(tmp_path):
    live = tmp_path / 'live'
    live.write_text('actual content')
    missing = tmp_path / 'missing'
    orphan = tmp_path / 'orphan'
    orphan.write_text('keep tracked')
    path = tmp_path / 'state.json'
    store = StateStore(path)
    store.record('local', ActionSpec('file', {'path': str(orphan)}))
    store.record('local', ActionSpec('file', {'path': str(missing)}))
    store._write()
    original = path.read_bytes()
    plan = Plan({'local': HostConfig('local')}, [TaskSpec('demo', ['local'], [
        ActionSpec('exec', {'command': 'must never execute'}, on_success=[
            ActionSpec('file', {'path': str(live), 'content': 'desired content'})])])])
    results = reconcile_state(plan, StateStore(path), dry_run=True)
    assert len(results) == 3
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.bak'))
    reconcile_state(plan, StateStore(path))
    assert live.read_text() == 'actual content'
    assert orphan.read_text() == 'keep tracked'
    assert not missing.exists()
    entries = json.loads(path.read_text())['local']
    assert set(entries) == {f'file.{live}', f'file.{orphan}'}
    assert len(list(tmp_path.glob('*.bak'))) == 1
    assert next(tmp_path.glob('*.bak')).read_bytes() == original
    assert path.stat().st_mode & 0o777 == 0o600


def test_reconcile_partial_package_list_and_probe_failure(tmp_path, monkeypatch):
    path = tmp_path / 'state.json'
    plan = Plan({'local': HostConfig('local')}, [TaskSpec('demo', ['local'], [
        ActionSpec('package', {'packages': ['installed', 'missing']})])])
    class Manager:
        def is_installed(self, executor, package):
            assert executor.dry_run
            return package == 'installed'
    monkeypatch.setattr('geppetto_automation.reconcile.PackageManagerFactory.create', lambda _: Manager())
    reconcile_state(plan, StateStore(path))
    assert set(json.loads(path.read_text())['local']) == {'package.installed'}
    original = path.read_bytes()
    def fail(*args):
        raise RuntimeError('rpm database failure')
    monkeypatch.setattr(Manager, 'is_installed', fail)
    with pytest.raises(RuntimeError, match='state file was not changed'):
        reconcile_state(plan, StateStore(path))
    assert path.read_bytes() == original


def test_reconcile_preserves_unsupported_and_other_hosts(tmp_path):
    path = tmp_path / 'state.json'
    store = StateStore(path)
    store.record('other', ActionSpec('file', {'path': '/other'}))
    store.record('local', ActionSpec('timezone', {'name': 'zone', 'timezone': 'Australia/Brisbane'}))
    store._write()
    original = path.read_bytes()
    reconcile_state(Plan({'local': HostConfig('local')}, []), StateStore(path))
    assert json.loads(path.read_bytes()) == json.loads(original)


def test_probe_executor_rejects_mutation_and_inventory_failure(tmp_path, monkeypatch):
    from geppetto_automation.reconcile import ProbeExecutor
    from geppetto_automation.executors import CommandResult
    executor = ProbeExecutor(HostConfig('local'), dry_run=True)
    with pytest.raises(RuntimeError, match='mutable command'):
        executor.run(['touch', str(tmp_path / 'must-not-exist')])
    assert not (tmp_path / 'must-not-exist').exists()
    monkeypatch.setattr('geppetto_automation.reconcile.LocalExecutor.run',
                        lambda *args, **kwargs: CommandResult(['rpm', '-q', 'jq'], '', 'rpm database unavailable', 2))
    with pytest.raises(RuntimeError, match='Live query failed'):
        executor.run(['rpm', '-q', 'jq'], mutable=False)
