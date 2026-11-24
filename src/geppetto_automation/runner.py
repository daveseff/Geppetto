from __future__ import annotations

import logging
from typing import Any, Optional

from .identity import resource_id
from .executors import AgentExecutor, Executor, LocalExecutor
from .operations import OPERATION_REGISTRY, Operation
from .types import ActionResult, ActionSpec, HostConfig, Plan, TaskSpec

logger = logging.getLogger(__name__)


class TaskRunner:
    """Coordinates the execution of automation tasks."""

    def __init__(self, plan: Plan, *, dry_run: bool = False, state_store=None, progress_callback=None, targets=None):
        self.targets = targets
        self.plan = plan
        self.dry_run = dry_run
        self.state_store = state_store
        self.progress_callback = progress_callback
        self._executors: dict[str, Executor] = {}

    def run(self) -> list[ActionResult]:
        if self.targets:
            return self._run_targets()
        results: list[ActionResult] = []
        for task in self.plan.tasks:
            results.extend(self._run_task(task))
        if self.state_store:
            results.extend(
                self.state_store.finalize(
                    self.plan,
                    self._executor_for,
                    persist=not self.dry_run,
                )
            )
        return results

    def _run_targets(self):
        from .targeting import select_targets
        nodes, order, requirements = select_targets(self.plan, self.targets)
        results = []
        failed = set()
        for index in order:
            node = nodes[index]
            host = self.plan.hosts[node.host]
            if requirements[index] & failed:
                failed.add(index)
                results.append(ActionResult(node.host, node.action.type, False,
                    "skipped: dependency failed", failed=True,
                    resource=self._resource_name(node.action.data)))
                continue
            batch = self._execute_action(node.action, host, self._executor_for(host))
            results.extend(batch)
            if any(result.failed for result in batch):
                failed.add(index)
        if self.state_store:
            # A partial apply must never garbage-collect unselected resources.
            self.state_store.finalize(self.plan, self._executor_for,
                                      persist=not self.dry_run, targeted=True)
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
                results.extend(self._execute_action(action, host, executor))
        return results

    def _execute_action(self, action: ActionSpec, host: HostConfig, executor: Executor, *, parent_target=None) -> list[ActionResult]:
        results: list[ActionResult] = []
        name = self._resource_name(action.data)
        address = parent_target or (f"{host.name}::{action.type}.{name}" if name else f"{host.name}::{resource_id(action)}")
        from .targeting import aliases
        dependencies = [dep if "::" in dep else f"{host.name}::{dep}" for dep in action.depends_on]
        if parent_target:
            dependencies.append(parent_target)
        references = [f"{host.name}::{ref}" for ref in aliases(action)]
        operation_cls = OPERATION_REGISTRY.get(action.type)
        if not operation_cls:
            detail = f"unknown operation '{action.type}'"
            logger.warning(detail)
            result = ActionResult(
                host=host.name,
                action=action.type,
                changed=False,
                details=detail,
                failed=True,
                resource=self._resource_name(action.data),
                target=address,
                dependencies=dependencies,
                references=references,
            )
            results.append(result)
            results.extend(self._run_child_actions(action.on_failure, host, executor, parent_target=address))
            return results

        try:
            operation: Operation = operation_cls(action.data)
        except Exception as exc:  # noqa: BLE001
            self._log_error("operation init failed", action, host, exc)
            result = ActionResult(
                host=host.name,
                action=action.type,
                changed=False,
                details=str(exc),
                failed=True,
                resource=self._resource_name(action.data),
                target=address,
                dependencies=dependencies,
                references=references,
            )
            results.append(result)
            results.extend(self._run_child_actions(action.on_failure, host, executor, parent_target=address))
            return results

        if self.progress_callback:
            try:
                self.progress_callback(host, action)
            except Exception:  # pragma: no cover
                logger.debug("progress callback failed", exc_info=True)
        try:
            result = operation.apply(host, executor)
        except Exception as exc:  # noqa: BLE001
            self._log_error("action failed", action, host, exc)
            result = ActionResult(
                host=host.name,
                action=action.type,
                changed=False,
                details=str(exc),
                failed=True,
                resource=self._resource_name(action.data),
                target=address,
                dependencies=dependencies,
                references=references,
            )
        else:
            if self.state_store and not result.failed:
                self.state_store.record(host.name, action)
        logger.debug("action=%s host=%s changed=%s", action.type, host.name, result.changed)
        if result.resource is None:
            result.resource = self._resource_name(action.data)
        result.dependencies = dependencies
        result.references = references
        result.target = address
        results.append(result)

        if not result.failed and result.changed:
            results.extend(self._run_child_actions(action.on_success, host, executor, parent_target=address))
        elif result.failed:
            results.extend(self._run_child_actions(action.on_failure, host, executor, parent_target=address))

        return results

    def _run_child_actions(self, actions: list[ActionSpec], host: HostConfig, executor: Executor, *, parent_target=None) -> list[ActionResult]:
        if not actions:
            return []
        ordered_actions = self._order_actions(actions)
        results: list[ActionResult] = []
        failed_refs = set()
        for child in ordered_actions:
            if self.targets and failed_refs.intersection(child.depends_on):
                batch = [ActionResult(host.name, child.type, False,
                    "skipped: dependency failed", failed=True,
                    resource=self._resource_name(child.data), target=parent_target)]
            else:
                batch = self._execute_action(child, host, executor, parent_target=parent_target)
            results.extend(batch)
            if self.targets and any(result.failed for result in batch):
                from .targeting import aliases
                failed_refs.update(aliases(child))
        return results

    def _log_error(self, message: str, action: ActionSpec, host: HostConfig, exc: Exception) -> None:
        if logger.isEnabledFor(logging.DEBUG):
            logger.error("action=%s host=%s %s: %s", action.type, host.name, message, exc, exc_info=True)
        else:
            logger.error("action=%s host=%s %s: %s", action.type, host.name, message, exc)

    def _executor_for(self, host: HostConfig) -> Executor:
        existing = self._executors.get(host.name)
        if existing is not None:
            return existing
        if host.connection == "local":
            executor = LocalExecutor(host, dry_run=self.dry_run)
            self._executors[host.name] = executor
            return executor
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
    def _resource_name(data: dict[str, Any]) -> Optional[str]:
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
        # Named dependencies remain compatible with older plans, including keys
        # whose identity now includes the user and key material.
        aliases = {}
        for aid, action in zip(ids, actions):
            name = self._resource_name(action.data)
            if name:
                aliases.setdefault(f"{action.type}.{name}", set()).add(aid)
        graph: dict[str, set[str]] = {aid: set() for aid in ids}
        in_degree: dict[str, int] = {aid: 0 for aid in ids}

        for aid, action in zip(ids, actions):
            deps = {resolved for dep in action.depends_on
                    for resolved in aliases.get(dep, {dep}) if resolved in id_map}
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
        identifier = resource_id(action)
        action.data["_resource_id"] = identifier
        return identifier
