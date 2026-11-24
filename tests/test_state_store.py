import json
import subprocess
from pathlib import Path

from geppetto_automation.inventory import InventoryLoader
from geppetto_automation.runner import TaskRunner
from geppetto_automation.state import StateStore
from geppetto_automation.types import HostConfig, Plan

PLAN_TEMPLATE = """
node 'local' {
  connection => local
}

task 'demo' on ['local'] {
  file { '%(path)s':
    ensure  => present
    content => "hello"
  }
}
"""


def test_state_store_removes_deleted_files(tmp_path: Path):
    plan_path = tmp_path / "plan.fops"
    target = tmp_path / "managed.txt"
    plan_path.write_text(PLAN_TEMPLATE % {"path": str(target)})

    loader = InventoryLoader()
    plan = loader.load(plan_path)
    state_path = plan_path.with_name("plan.fops.state.json")
    state_store = StateStore(state_path)

    runner = TaskRunner(plan, state_store=state_store)
    first_results = runner.run()

    assert target.exists()
    assert state_path.exists()
    assert (state_path.stat().st_mode & 0o777) == 0o600
    assert any(res.changed and not res.failed for res in first_results)

    # Rewrite plan with no tasks to trigger cleanup
    plan_path.write_text("node 'local' { connection => local }\n")
    plan = loader.load(plan_path)
    state_store = StateStore(state_path)
    runner = TaskRunner(plan, state_store=state_store)
    second_results = runner.run()

    assert not target.exists()
    data = state_path.read_text()
    assert '"local"' not in data or data.strip() == '{}'
    assert any(res.changed and "removed" in res.details for res in second_results)


def test_dry_run_previews_cleanup_without_changing_resource_or_state(tmp_path: Path):
    plan_path = tmp_path / "plan.fops"
    target = tmp_path / "managed.txt"
    plan_path.write_text(PLAN_TEMPLATE % {"path": str(target)})
    loader = InventoryLoader()
    state_path = tmp_path / "state.json"

    TaskRunner(loader.load(plan_path), state_store=StateStore(state_path)).run()
    original_state = state_path.read_text()
    plan_path.write_text("node 'local' { connection => local }\n")

    results = TaskRunner(
        loader.load(plan_path),
        dry_run=True,
        state_store=StateStore(state_path),
    ).run()

    assert target.exists()
    assert state_path.read_text() == original_state
    assert any(result.changed and result.details == "removed" for result in results)


def test_dry_run_previews_multiple_removed_crontab_entries(tmp_path: Path, monkeypatch):
    cron_lines = [
        "0 5 * * * /usr/sbin/aide --check",
        "0 2 * * 3,5 /usr/local/bin/copy_snapshot billing",
        "0 2 * * 3,5 /usr/local/bin/copy_snapshot policy",
        "0 2 * * 3,5 /usr/local/bin/copy_snapshot claim",
    ]
    entries = {}
    for index, line in enumerate(cron_lines):
        fields = line.split(None, 5)
        resource_id = f"cron.job-{index}"
        spec = {
            "name": f"job-{index}",
            "target": "crontab_entry",
            "user": "root",
            "minute": fields[0],
            "hour": fields[1],
            "day": fields[2],
            "month": fields[3],
            "weekday": fields[4],
            "command": fields[5],
            "_resource_id": resource_id,
        }
        entries[resource_id] = {
            "action": "cron",
            "spec": spec,
            "resource_id": resource_id,
            "depends_on": [],
        }

    state_path = tmp_path / "state.json"
    state_data = {"npjump": entries}
    state_path.write_text(json.dumps(state_data))
    monkeypatch.setattr(
        "geppetto_automation.executors.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, "\n".join(cron_lines) + "\n", ""
        ),
    )
    plan = Plan(hosts={"npjump": HostConfig("npjump")}, tasks=[])

    results = TaskRunner(plan, dry_run=True, state_store=StateStore(state_path)).run()

    assert len(results) == 4
    assert all(result.changed and result.details == "removed" for result in results)
    assert json.loads(state_path.read_text()) == state_data


def test_legacy_bulk_packages_migrate_without_removing_required_members(tmp_path, monkeypatch):
    from geppetto_automation.types import ActionSpec, TaskSpec, ActionResult
    state_path = tmp_path / 'state.json'
    state_path.write_text(json.dumps({'local': {
        'package.__2': {'action': 'package', 'spec': {'packages': ['jq', 'rsync', 'old-package'], '_resource_id': 'package.__2'}},
        'package.__1': {'action': 'package', 'spec': {'packages': ['newrelic-infra'], '_resource_id': 'package.__1'}},
    }}))
    plan = Plan({'local': HostConfig('local')}, [
        TaskSpec('packages', ['local'], [ActionSpec('package', {'packages': ['rsync', 'jq', 'new-package']})]),
        TaskSpec('newrelic', ['local'], [ActionSpec('package', {'packages': ['newrelic-infra']})]),
    ])
    calls = []
    class Package:
        def __init__(self, spec):
            self.spec = spec
        def apply(self, host, executor):
            calls.append(self.spec)
            return ActionResult(host.name, 'package', True, 'ok')
    monkeypatch.setitem(__import__('geppetto_automation.runner', fromlist=['OPERATION_REGISTRY']).OPERATION_REGISTRY, 'package', Package)
    TaskRunner(plan, state_store=StateStore(state_path)).run()
    removals = [spec['name'] for spec in calls if spec.get('state') == 'absent']
    assert removals == ['old-package']
    assert set(json.loads(state_path.read_text())['local']) == {
        'package.jq', 'package.rsync', 'package.new-package', 'package.newrelic-infra'}


def test_skipped_hook_and_failed_action_remain_tracked(tmp_path, monkeypatch):
    from geppetto_automation.types import ActionSpec, TaskSpec, ActionResult
    path = tmp_path / 'state.json'
    store = StateStore(path)
    child = ActionSpec('file', {'path': str(tmp_path / 'child')})
    failing = ActionSpec('file', {'path': str(tmp_path / 'failing')})
    store.record('local', child)
    store.record('local', failing)
    store._write()
    class File:
        def __init__(self, spec):
            self.spec = spec
        def apply(self, host, executor):
            assert self.spec.get('state') != 'absent'
            return ActionResult(host.name, 'file', False, 'failed', failed=True)
    class Parent:
        def __init__(self, spec): pass
        def apply(self, host, executor):
            return ActionResult(host.name, 'exec', False, 'noop')
    from geppetto_automation.runner import OPERATION_REGISTRY
    monkeypatch.setitem(OPERATION_REGISTRY, 'file', File)
    monkeypatch.setitem(OPERATION_REGISTRY, 'exec', Parent)
    plan = Plan({'local': HostConfig('local')}, [TaskSpec('demo', ['local'], [
        ActionSpec('exec', {'name': 'parent'}, on_success=[child]), failing])])
    results = TaskRunner(plan, state_store=StateStore(path)).run()
    assert len(results) == 2
    assert len(json.loads(path.read_text())['local']) == 2


def test_key_rotation_cleanup_preserves_shared_keys(tmp_path):
    from geppetto_automation.types import ActionSpec, TaskSpec
    path = tmp_path / 'state.json'
    store = StateStore(path)
    store.record('local', ActionSpec('authorized_key', {'user': 'ansible', 'name': 'keys', 'key': 'ssh-rsa AAA\nssh-rsa BBB'}))
    store._write()
    store = StateStore(path)
    action = ActionSpec('authorized_key', {'user': 'ansible', 'name': 'renamed', 'key': 'ssh-rsa BBB\nssh-rsa CCC'})
    store.record('local', action)
    removed = []
    store._destroy_entry = lambda host, entry, factory: removed.append(entry['spec']['key'])
    plan = Plan({'local': HostConfig('local')}, [TaskSpec('keys', ['local'], [action])])
    store.finalize(plan, None, persist=False)
    assert removed == ['ssh-rsa AAA']
