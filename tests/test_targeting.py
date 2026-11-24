from pathlib import Path
import json

import pytest

from geppetto_automation.runner import TaskRunner
from geppetto_automation.state import StateStore
from geppetto_automation.targeting import select_targets
from geppetto_automation.types import ActionResult, ActionSpec, HostConfig, Plan, TaskSpec


def plan_with(actions):
    return Plan({'local': HostConfig('local')}, [TaskSpec('demo', ['local'], actions)])


def test_target_applies_one_file_and_preserves_unselected_and_orphan_state(tmp_path):
    first, second, orphan = [tmp_path / name for name in ('first', 'second', 'orphan')]
    for path in (first, second, orphan):
        path.write_text('old')
    state_path = tmp_path / 'state.json'
    store = StateStore(state_path)
    for path in (first, second, orphan):
        store.record('local', ActionSpec('file', {'path': str(path), 'content': 'old'}))
    store._write()
    before = json.loads(state_path.read_text())
    plan = plan_with([ActionSpec('file', {'path': str(path), 'content': 'new'}) for path in (first, second)])
    TaskRunner(plan, state_store=StateStore(state_path), targets=[f'file.{first}']).run()
    assert first.read_text() == 'new'
    assert second.read_text() == orphan.read_text() == 'old'
    after = json.loads(state_path.read_text())
    assert after['local'][f'file.{second}'] == before['local'][f'file.{second}']
    assert after['local'][f'file.{orphan}'] == before['local'][f'file.{orphan}']
    assert set(after['local']) == set(before['local'])


def test_target_dry_run_does_not_change_resources_or_state(tmp_path):
    path = tmp_path / 'file'
    path.write_text('old')
    state = tmp_path / 'state.json'
    state.write_text('{}')
    plan = plan_with([ActionSpec('file', {'path': str(path), 'content': 'new'})])
    results = TaskRunner(plan, dry_run=True, state_store=StateStore(state), targets=[f'file.{path}']).run()
    assert results[0].changed
    assert path.read_text() == 'old'
    assert state.read_text() == '{}'


def test_target_includes_transitive_dependencies_across_tasks():
    plan = Plan({'local': HostConfig('local')}, [
        TaskSpec('keys', ['local'], [ActionSpec('authorized_key', {'name': 'ansible-exec', 'user': 'ansible', 'key': 'ssh-rsa AAA'}, depends_on=['user.ansible'])]),
        TaskSpec('users', ['local'], [ActionSpec('user', {'name': 'ansible'}, depends_on=['group.ops'])]),
        TaskSpec('groups', ['local'], [ActionSpec('group', {'name': 'ops'})]),
    ])
    nodes, order, deps = select_targets(plan, ['authorized_key.ansible-exec'])
    assert [nodes[i].action.type for i in order] == ['group', 'user', 'authorized_key']
    assert len(deps[order[-1]]) == 1


def test_target_individual_package_and_bulk_resource():
    from geppetto_automation.identity import resource_id
    action = ActionSpec('package', {'packages': ['jq', 'rsync']})
    plan = plan_with([action])
    nodes, order, _ = select_targets(plan, ['package.jq'])
    assert [nodes[i].action.data['packages'] for i in order] == [['jq']]
    nodes, order, _ = select_targets(plan, [resource_id(action)])
    assert [nodes[i].action.data['packages'] for i in order] == [['jq', 'rsync']]


def test_multiple_targets_are_deduplicated():
    plan = plan_with([ActionSpec('file', {'path': '/one'}), ActionSpec('file', {'path': '/two'})])
    _, order, _ = select_targets(plan, ['file./one', 'file./two', 'file./one'])
    assert len(order) == 2


@pytest.mark.parametrize('kind', ['missing-target', 'missing-dependency', 'cycle', 'ambiguous'])
def test_invalid_selection_fails_before_any_resource_changes(tmp_path, kind):
    target = tmp_path / 'must-not-exist'
    action = ActionSpec('file', {'path': str(target), 'content': 'new'})
    plan = plan_with([action])
    selector = f'file.{target}'
    if kind == 'missing-target':
        targets = [selector, 'file.missing']
    elif kind == 'missing-dependency':
        action.depends_on = ['user.missing']
        targets = [selector]
    elif kind == 'cycle':
        action.depends_on = [selector]
        targets = [selector]
    else:
        plan.tasks.append(TaskSpec('other', ['local'], [ActionSpec('file', dict(action.data))]))
        targets = [selector]
    with pytest.raises(ValueError):
        TaskRunner(plan, targets=targets).run()
    assert not target.exists()


def test_host_qualified_target():
    plan = Plan({name: HostConfig(name) for name in ('one', 'two')}, [
        TaskSpec('demo', ['one', 'two'], [ActionSpec('user', {'name': 'ansible'})])])
    with pytest.raises(ValueError, match='Ambiguous'):
        select_targets(plan, ['user.ansible'])
    nodes, order, _ = select_targets(plan, ['two::user.ansible'])
    assert [nodes[i].host for i in order] == ['two']


def test_dependency_failure_skips_target_but_runs_independent_target(monkeypatch):
    calls = []
    class Recording:
        def __init__(self, spec): self.spec = spec
        def apply(self, host, executor):
            name = self.spec['name']
            calls.append(name)
            return ActionResult(host.name, 'record', True, 'result', failed=name == 'dependency')
    monkeypatch.setitem(__import__('geppetto_automation.runner', fromlist=['OPERATION_REGISTRY']).OPERATION_REGISTRY, 'record', Recording)
    plan = plan_with([
        ActionSpec('record', {'name': 'target'}, depends_on=['record.dependency']),
        ActionSpec('record', {'name': 'dependency'}),
        ActionSpec('record', {'name': 'independent'}),
    ])
    results = TaskRunner(plan, targets=['record.target', 'record.independent']).run()
    assert calls == ['dependency', 'independent']
    assert any(r.resource == 'target' and r.failed and 'dependency failed' in r.details for r in results)


def test_target_keeps_hooks_conditional_and_refuses_direct_hook(tmp_path):
    parent, child = tmp_path / 'parent', tmp_path / 'child'
    action = ActionSpec('file', {'path': str(parent), 'content': 'parent'}, on_success=[
        ActionSpec('file', {'path': str(child), 'content': 'child'})])
    plan = plan_with([action])
    with pytest.raises(ValueError, match='conditional hook'):
        TaskRunner(plan, targets=[f'file.{child}']).run()
    TaskRunner(plan, targets=[f'file.{parent}']).run()
    assert parent.exists() and child.exists()
    child.unlink()
    TaskRunner(plan, targets=[f'file.{parent}']).run()
    assert not child.exists()



def test_bulk_package_hooks_run_once_for_multiple_selected_members(monkeypatch):
    calls = []
    class Recording:
        def __init__(self, spec): self.spec = spec
        def apply(self, host, executor):
            calls.append(self.spec)
            return ActionResult(host.name, 'test', True, 'changed')
    from geppetto_automation.runner import OPERATION_REGISTRY
    monkeypatch.setitem(OPERATION_REGISTRY, 'package', Recording)
    monkeypatch.setitem(OPERATION_REGISTRY, 'exec', Recording)
    plan = plan_with([ActionSpec('package', {'packages': ['jq', 'rsync', 'unzip']},
                               on_success=[ActionSpec('exec', {'name': 'hook', 'command': 'unused'})])])
    TaskRunner(plan, targets=['package.jq', 'package.rsync']).run()
    assert len(calls) == 2
    assert calls[0]['packages'] == ['jq', 'rsync']
    assert calls[1]['name'] == 'hook'


def test_failed_hook_prerequisite_skips_dependent_hook(monkeypatch):
    calls = []
    class Recording:
        def __init__(self, spec): self.spec = spec
        def apply(self, host, executor):
            calls.append(self.spec['name'])
            return ActionResult(host.name, 'record', True, 'test', failed=self.spec['name'] == 'failed')
    from geppetto_automation.runner import OPERATION_REGISTRY
    monkeypatch.setitem(OPERATION_REGISTRY, 'record', Recording)
    plan = plan_with([ActionSpec('record', {'name': 'parent'}, on_success=[
        ActionSpec('record', {'name': 'failed'}),
        ActionSpec('record', {'name': 'dependent'}, depends_on=['record.failed'])])])
    results = TaskRunner(plan, targets=['record.parent']).run()
    assert calls == ['parent', 'failed']
    assert results[-1].failed and results[-1].resource == 'dependent'
    assert all(result.target == 'local::record.parent' for result in results)


def test_hook_dependency_cycle_rejected_before_execution(tmp_path):
    path = tmp_path / 'must-not-exist'
    parent = ActionSpec('file', {'path': str(path), 'content': 'new'}, on_success=[
        ActionSpec('exec', {'name': 'one'}, depends_on=['exec.two']),
        ActionSpec('exec', {'name': 'two'}, depends_on=['exec.one'])])
    with pytest.raises(ValueError, match='cycle'):
        TaskRunner(plan_with([parent]), targets=[f'file.{path}']).run()
    assert not path.exists()
