import pytest

from geppetto_automation.cli import dry_run_layout, format_result
from geppetto_automation.operations.authorized_key import AuthorizedKeyManager
from geppetto_automation.operations.user import UserManager
from geppetto_automation.runner import TaskRunner
from geppetto_automation.types import ActionResult, ActionSpec, HostConfig, Plan, TaskSpec


def missing_user(self, name):
    raise ValueError(f"User '{name}' does not exist")


def test_user_creation_is_simulated_for_both_dependent_keys(monkeypatch):
    monkeypatch.setattr(UserManager, 'get', lambda self, name: None)
    monkeypatch.setattr(AuthorizedKeyManager, 'get_user', missing_user)
    def forbidden(*args, **kwargs):
        raise AssertionError('dry-run must not create users or write authorized_keys')
    monkeypatch.setattr('geppetto_automation.executors.subprocess.run', forbidden)
    monkeypatch.setattr(AuthorizedKeyManager, 'write', forbidden)
    actions = [ActionSpec('user', {'name': 'ansible'}), *[
        ActionSpec('authorized_key', {'name': name, 'user': 'ansible', 'key': key}, depends_on=['user.ansible'])
        for name, key in [('ansible-exec', 'ssh-rsa AAA'), ('ansible-management', 'ssh-ed25519 BBB')]]]
    plan = Plan({'local': HostConfig('local')}, [TaskSpec('users', ['local'], actions)])
    results = TaskRunner(plan, dry_run=True).run()
    assert len(results) == 3
    assert all(result.changed and not result.failed for result in results)
    assert all('planned user creation' in result.details for result in results[1:])
    depths, context = dry_run_layout(results)
    assert depths == {0: 0, 1: 1, 2: 1}
    assert context == {0, 1, 2}
    assert format_result(results[1], dry_run=True, depth=depths[1]).startswith('    \\_ ')
    assert 'depends on: user.ansible' in format_result(results[1], dry_run=True, depth=1)
    assert not format_result(results[1]).startswith('\\_ ')
    assert 'depends on:' not in format_result(results[1])


def test_missing_user_without_successful_creation_remains_an_error(monkeypatch):
    monkeypatch.setattr(AuthorizedKeyManager, 'get_user', missing_user)
    plan = Plan({'local': HostConfig('local')}, [TaskSpec('keys', ['local'], [
        ActionSpec('authorized_key', {'name': 'ansible', 'user': 'ansible', 'key': 'ssh-rsa AAA'})])])
    results = TaskRunner(plan, dry_run=True).run()
    assert results[0].failed
    assert "User 'ansible' does not exist" in results[0].details


def test_failed_user_creation_does_not_simulate_an_account(monkeypatch):
    monkeypatch.setattr(UserManager, 'get', lambda self, name: None)
    def fail(*args, **kwargs):
        raise RuntimeError('creation failed')
    monkeypatch.setattr(UserManager, 'add', fail)
    monkeypatch.setattr(AuthorizedKeyManager, 'get_user', missing_user)
    actions = [ActionSpec('user', {'name': 'ansible'}),
               ActionSpec('authorized_key', {'name': 'ansible', 'user': 'ansible', 'key': 'ssh-rsa AAA'}, depends_on=['user.ansible'])]
    plan = Plan({'local': HostConfig('local')}, [TaskSpec('users', ['local'], actions)])
    assert all(result.failed for result in TaskRunner(plan, dry_run=True).run())


def test_layout_keeps_noop_prerequisites_and_shows_transitive_depth():
    results = [
        ActionResult('local', 'group', False, 'noop', references=['local::group.ops']),
        ActionResult('local', 'user', False, 'noop', dependencies=['local::group.ops'], references=['local::user.ansible']),
        ActionResult('local', 'authorized_key', True, 'added', dependencies=['local::user.ansible'], references=['local::authorized_key.key']),
        ActionResult('other', 'user', False, 'noop', references=['other::user.ansible']),
    ]
    depths, context = dry_run_layout(results)
    assert depths == {0: 0, 1: 1, 2: 2, 3: 0}
    assert context == {0, 1, 2}
    assert format_result(results[2], dry_run=True, depth=2).startswith('        \\_ ')


def test_layout_handles_multiple_prerequisites_and_cycles():
    first = ActionResult('local', 'file', True, 'changed', references=['local::file.one'], dependencies=['local::file.two'])
    second = ActionResult('local', 'file', True, 'changed', references=['local::file.two'], dependencies=['local::file.one'])
    depths, context = dry_run_layout([first, second])
    assert context == {0, 1}
    assert all(isinstance(value, int) for value in depths.values())
