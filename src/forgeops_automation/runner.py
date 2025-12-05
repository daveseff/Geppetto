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
        for host_name in task.hosts:
            host = self.plan.hosts.get(host_name)
            if not host:
                raise KeyError(f"Host '{host_name}' is not defined")
            executor = self._executor_for(host)
            for action in task.actions:
                operation_cls = OPERATION_REGISTRY.get(action.type)
                if not operation_cls:
                    raise KeyError(f"Operation '{action.type}' is not registered")
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
                    )
                else:
                    if self.state_store and not self.dry_run:
                        self.state_store.record(host.name, action.type, action.data)
                logger.debug(
                    "action=%s host=%s changed=%s", action.type, host.name, result.changed
                )
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
