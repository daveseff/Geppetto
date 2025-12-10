from geppetto_automation import runner as runner_mod
from geppetto_automation.types import ActionResult, ActionSpec, HostConfig, Plan, TaskSpec


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
        ActionSpec(type="record", data={"name": "user.geppetto"}, depends_on=[]),
        ActionSpec(
            type="record",
            data={"name": "authorized_key.geppetto-admin"},
            depends_on=["record.user.geppetto"],
        ),
    ]
    task = TaskSpec(name="demo", hosts=["local"], actions=actions)
    plan = Plan(hosts=hosts, tasks=[task])

    monkeypatch.setattr("geppetto_automation.runner.OPERATION_REGISTRY", {"record": RecordingOperation})

    runner = runner_mod.TaskRunner(plan)
    runner.run()

    assert order == ["user.geppetto", "authorized_key.geppetto-admin"]


def test_runner_executes_on_success_children(monkeypatch):
    calls: list[str] = []

    class ParentOp:
        def __init__(self, spec: dict):
            self.name = spec.get("name")

        def apply(self, host: HostConfig, executor):  # noqa: ARG002
            calls.append("parent")
            return ActionResult(host=host.name, action="parent", changed=True, details="ok")

    class ChildOp:
        def __init__(self, spec: dict):
            self.name = spec.get("name")

        def apply(self, host: HostConfig, executor):  # noqa: ARG002
            calls.append(f"child:{self.name}")
            return ActionResult(host=host.name, action=self.name or "", changed=True, details="ok")

    hosts = {"local": HostConfig(name="local")}
    child = ActionSpec(type="child", data={"name": "apply"}, depends_on=[])
    parent = ActionSpec(type="parent", data={"name": "set-policy"}, depends_on=[], on_success=[child])
    task = TaskSpec(name="demo", hosts=["local"], actions=[parent])
    plan = Plan(hosts=hosts, tasks=[task])

    monkeypatch.setattr(
        "geppetto_automation.runner.OPERATION_REGISTRY",
        {"parent": ParentOp, "child": ChildOp},
    )

    runner = runner_mod.TaskRunner(plan)
    results = runner.run()

    assert calls == ["parent", "child:apply"]
    assert [r.action for r in results] == ["parent", "apply"]


def test_runner_executes_on_failure_children(monkeypatch):
    calls: list[str] = []

    class ParentOp:
        def __init__(self, spec: dict):
            self.spec = spec

        def apply(self, host: HostConfig, executor):  # noqa: ARG002
            calls.append("parent")
            return ActionResult(host=host.name, action="parent", changed=False, details="boom", failed=True)

    class ChildOp:
        def __init__(self, spec: dict):
            self.name = spec.get("name")

        def apply(self, host: HostConfig, executor):  # noqa: ARG002
            calls.append(f"child:{self.name}")
            return ActionResult(host=host.name, action=self.name or "", changed=True, details="handled")

    hosts = {"local": HostConfig(name="local")}
    child = ActionSpec(type="child", data={"name": "cleanup"}, depends_on=[])
    parent = ActionSpec(type="parent", data={}, depends_on=[], on_failure=[child])
    task = TaskSpec(name="demo", hosts=["local"], actions=[parent])
    plan = Plan(hosts=hosts, tasks=[task])

    monkeypatch.setattr(
        "geppetto_automation.runner.OPERATION_REGISTRY",
        {"parent": ParentOp, "child": ChildOp},
    )

    runner = runner_mod.TaskRunner(plan)
    results = runner.run()

    assert calls == ["parent", "child:cleanup"]
    assert results[0].failed is True
    assert [r.action for r in results] == ["parent", "cleanup"]


def test_on_success_skips_when_no_change(monkeypatch):
    calls: list[str] = []

    class ParentOp:
        def __init__(self, spec: dict):
            self.spec = spec

        def apply(self, host: HostConfig, executor):  # noqa: ARG002
            calls.append("parent")
            return ActionResult(host=host.name, action="parent", changed=False, details="noop")

    class ChildOp:
        def __init__(self, spec: dict):
            self.spec = spec

        def apply(self, host: HostConfig, executor):  # noqa: ARG002
            calls.append("child")
            return ActionResult(host=host.name, action="child", changed=True, details="ok")

    hosts = {"local": HostConfig(name="local")}
    child = ActionSpec(type="child", data={}, depends_on=[])
    parent = ActionSpec(type="parent", data={}, depends_on=[], on_success=[child])
    task = TaskSpec(name="demo", hosts=["local"], actions=[parent])
    plan = Plan(hosts=hosts, tasks=[task])

    monkeypatch.setattr(
        "geppetto_automation.runner.OPERATION_REGISTRY",
        {"parent": ParentOp, "child": ChildOp},
    )

    runner = runner_mod.TaskRunner(plan)
    results = runner.run()

    assert calls == ["parent"]
    assert [r.action for r in results] == ["parent"]


def test_runner_handles_operation_init_failure(monkeypatch):
    hosts = {"local": HostConfig(name="local")}

    class BadOp:
        def __init__(self, spec: dict):  # noqa: ARG002
            raise ValueError("bad init")

    task = TaskSpec(
        name="demo",
        hosts=["local"],
        actions=[ActionSpec(type="bad", data={}, depends_on=[])],
    )
    plan = Plan(hosts=hosts, tasks=[task])

    monkeypatch.setattr("geppetto_automation.runner.OPERATION_REGISTRY", {"bad": BadOp})

    runner = runner_mod.TaskRunner(plan)
    results = runner.run()

    assert len(results) == 1
    assert results[0].failed is True
    assert "bad init" in results[0].details
