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
        actions=[ActionSpec(type="dummy", data={"action": "dummy"}, depends_on=[])],
    )
    plan = Plan(hosts=hosts, tasks=[task])

    monkeypatch.setattr(runner_mod, "OPERATION_REGISTRY", {"dummy": DummyOperation})

    runner = runner_mod.TaskRunner(plan)
    results = runner.run()

    assert len(results) == 1
    assert results[0].action == "dummy"


def test_runner_honors_depends_on(monkeypatch):
    order: list[str] = []

    class RecordingOperation:
        def __init__(self, spec: dict):
            self.name = spec.get("name")

        def apply(self, host: HostConfig, executor):
            order.append(self.name)
            return ActionResult(host=host.name, action=self.name or "", changed=True, details="ok")

    hosts = {"local": HostConfig(name="local")}
    actions = [
        ActionSpec(type="record", data={"name": "user.forgeops"}, depends_on=[]),
        ActionSpec(
            type="record",
            data={"name": "authorized_key.forgeops-admin"},
            depends_on=["record.user.forgeops"],
        ),
    ]
    task = TaskSpec(name="demo", hosts=["local"], actions=actions)
    plan = Plan(hosts=hosts, tasks=[task])

    monkeypatch.setattr("forgeops_automation.runner.OPERATION_REGISTRY", {"record": RecordingOperation})

    runner = runner_mod.TaskRunner(plan)
    runner.run()

    assert order == ["user.forgeops", "authorized_key.forgeops-admin"]
