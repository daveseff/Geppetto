from __future__ import annotations

import logging

from .executors import AgentExecutor, Executor, LocalExecutor
from .operations import OPERATION_REGISTRY, Operation
from .types import ActionResult, HostConfig, Plan, TaskSpec

logger = logging.getLogger(__name__)


class TaskRunner:
    """Coordinates the execution of automation tasks."""

    def __init__(self, plan: Plan, *, dry_run: bool = False, state_store=None):
        self.plan = plan
        self.dry_run = dry_run
        self.state_store = state_store

    def run(self) -> list[ActionResult]:
        results: list[ActionResult] = []
        for task in self.plan.tasks:
            results.extend(self._run_task(task))
        if self.state_store and not self.dry_run:
            self.state_store.finalize(self.plan, self._executor_for)
        return results

    def _run_task(self, task: TaskSpec) -> list[ActionResult]:
        results: list[ActionResult] = []
        logger.debug("task=%s hosts=%s", task.name, ",".join(task.hosts))
        ordered_actions = self._order_actions(task.actions)
        for host_name in task.hosts:
            host = self.plan.hosts.get(host_name)
            if not host:
                raise KeyError(f"Host '{host_name}' is not defined")
            executor = self._executor_for(host)
            for action in ordered_actions:
                operation_cls = OPERATION_REGISTRY.get(action.type)
                if not operation_cls:
                    detail = f"unknown operation '{action.type}'"
                    logger.warning(detail)
                    results.append(
                        ActionResult(
                            host=host.name,
                            action=action.type,
                            changed=False,
                            details=detail,
                            failed=True,
                            resource=self._resource_name(action.data),
                        )
                    )
                    continue
                operation: Operation = operation_cls(action.data)
                try:
                    result = operation.apply(host, executor)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "action=%s host=%s failed: %s", action.type, host.name, exc, exc_info=True
                    )
                    result = ActionResult(
                        host=host.name,
                        action=action.type,
                        changed=False,
                        details=str(exc),
                        failed=True,
                        resource=self._resource_name(action.data),
                    )
                else:
                    if self.state_store and not self.dry_run:
                        self.state_store.record(host.name, action)
                logger.debug(
                    "action=%s host=%s changed=%s", action.type, host.name, result.changed
                )
                if result.resource is None:
                    result.resource = self._resource_name(action.data)
                results.append(result)
        return results

    def _executor_for(self, host: HostConfig) -> Executor:
        if host.connection == "local":
            return LocalExecutor(host, dry_run=self.dry_run)
        if host.connection == "agent":
            raise NotImplementedError(
                "Agent connection requested but no AgentExecutor is available yet"
            )
        if host.connection == "server":
            raise NotImplementedError(
                "Server mediated orchestration will be added in a future revision"
            )
        raise ValueError(f"Unknown connection type '{host.connection}'")

    @staticmethod
    def _resource_name(data: dict[str, Any]) -> str | None:
        for key in ("resource", "name", "path", "mount_point", "user", "service"):
            value = data.get(key)
            if value:
                return str(value)
        return None

    def _order_actions(self, actions: list[ActionSpec]) -> list[ActionSpec]:
        if not actions:
            return []
        ids = [self._action_id(action, idx) for idx, action in enumerate(actions, start=1)]
        id_map = dict(zip(ids, actions))
        graph: dict[str, set[str]] = {aid: set() for aid in ids}
        in_degree: dict[str, int] = {aid: 0 for aid in ids}

        for aid, action in zip(ids, actions):
            deps = {dep for dep in action.depends_on if dep in id_map}
            graph[aid] = deps
            in_degree[aid] = len(deps)

        queue = [aid for aid, deg in in_degree.items() if deg == 0]
        ordered_ids: list[str] = []
        while queue:
            current = queue.pop(0)
            ordered_ids.append(current)
            for node, deps in graph.items():
                if current in deps:
                    in_degree[node] -= 1
                    if in_degree[node] == 0:
                        queue.append(node)

        # Append any remaining nodes (due to cycles or external deps) in original order
        seen = set(ordered_ids)
        for aid in ids:
            if aid not in seen:
                ordered_ids.append(aid)

        return [id_map[aid] for aid in ordered_ids]

    def _action_id(self, action: ActionSpec, index: int) -> str:
        name = self._resource_name(action.data)
        if name:
            identifier = f"{action.type}.{name}"
        else:
            identifier = f"{action.type}.__{index}"
        action.data.setdefault("_resource_id", identifier)
        return identifier
