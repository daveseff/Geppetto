from pathlib import Path

from forgeops_automation.inventory import InventoryLoader
from forgeops_automation.runner import TaskRunner
from forgeops_automation.state import StateStore
from forgeops_automation.types import HostConfig

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
    runner.run()

    assert target.exists()
    assert state_path.exists()

    # Rewrite plan with no tasks to trigger cleanup
    plan_path.write_text("node 'local' { connection => local }\n")
    plan = loader.load(plan_path)
    state_store = StateStore(state_path)
    runner = TaskRunner(plan, state_store=state_store)
    runner.run()

    assert not target.exists()
    data = state_path.read_text()
    assert '"local"' not in data or data.strip() == '{}'
