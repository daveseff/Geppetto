from forgeops_automation import runner as runner_mod
from forgeops_automation.types import ActionResult, ActionSpec, HostConfig, Plan, TaskSpec


class DummyOperation:
    def __init__(self, spec: dict):
        self.spec = spec

    def apply(self, host: HostConfig, executor):
        return ActionResult(host=host.name, action=self.spec["action"], changed=True, details="ok")


def test_runner_invokes_registered_operations(monkeypatch):
    hosts = {"local": HostConfig(name="local")}
    task = TaskSpec(
        name="demo",
        hosts=["local"],
        actions=[ActionSpec(type="dummy", data={"action": "dummy"})],
    )
    plan = Plan(hosts=hosts, tasks=[task])

    monkeypatch.setattr(runner_mod, "OPERATION_REGISTRY", {"dummy": DummyOperation})

    runner = runner_mod.TaskRunner(plan)
    results = runner.run()

    assert len(results) == 1
    assert results[0].action == "dummy"
