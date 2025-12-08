from __future__ import annotations

from pathlib import Path
from typing import Any
import re
import tomllib

from .dsl import DSLParseError, DSLParser
from .types import ActionSpec, HostConfig, Plan, TaskSpec


class InventoryLoader:
    """Loads plan definitions from TOML files."""

    INCLUDE_RE = re.compile(r"^include\s+['\"]([^'\"]+)['\"]\s*$")

    def load(self, path: Path) -> Plan:
        path = Path(path)
        suffix = path.suffix.lower()
        base_dir = path.parent
        try:
            if suffix == ".toml":
                plan = self._load_toml(path)
            elif suffix in {".fops", ".pp"}:
                text = self._read_with_includes(path)
                plan = DSLParser().parse_text(text)
            else:
                text = path.read_text()
                try:
                    plan = DSLParser().parse_text(text)
                except DSLParseError:
                    data = tomllib.loads(text)
                    hosts = self._parse_hosts(data.get("hosts", {}))
                    tasks = self._parse_tasks(data.get("tasks", []), hosts)
                    plan = Plan(hosts=hosts, tasks=tasks)
        except DSLParseError as exc:
            line = f"{exc.line}:{exc.column}" if exc.line is not None else "?"
            raise DSLParseError(f"{path}:{line} {exc}") from None
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"{path}:{exc.lineno}:{exc.colno} {exc.msg}") from None

        self._attach_plan_dir(plan, base_dir)
        return plan

    def _load_toml(self, path: Path) -> Plan:
        data = tomllib.loads(path.read_text())
        hosts = self._parse_hosts(data.get("hosts", {}))
        tasks = self._parse_tasks(data.get("tasks", []), hosts)
        return Plan(hosts=hosts, tasks=tasks)

    @staticmethod
    def _parse_hosts(host_data: dict[str, Any]) -> dict[str, HostConfig]:
        if not host_data:
            host_data = {"local": {"connection": "local"}}
        hosts: dict[str, HostConfig] = {}
        for name, payload in host_data.items():
            hosts[name] = HostConfig(
                name=name,
                connection=payload.get("connection", "local"),
                address=payload.get("address"),
                variables=payload.get("variables", {}),
            )
        return hosts

    @staticmethod
    def _parse_tasks(raw_tasks: list[dict[str, Any]], hosts: dict[str, HostConfig]) -> list[TaskSpec]:
        tasks: list[TaskSpec] = []
        for index, task in enumerate(raw_tasks, start=1):
            name = task.get("name", f"task-{index}")
            target_hosts = task.get("hosts") or list(hosts.keys())
            actions = [InventoryLoader._parse_action(action, index, pos) for pos, action in enumerate(task.get("actions", []), start=1)]
            tasks.append(TaskSpec(name=name, hosts=target_hosts, actions=actions))
        return tasks

    @staticmethod
    def _parse_action(action: dict[str, Any], task_index: int, action_index: int) -> ActionSpec:
        action_type = action.get("type")
        if not action_type:
            raise ValueError(f"Task {task_index} action {action_index} is missing a type")
        depends = action.get("depends_on", [])
        if isinstance(depends, str):
            depends_list = [depends]
        else:
            depends_list = list(depends or [])
        data = {k: v for k, v in action.items() if k not in {"type", "depends_on"}}
        return ActionSpec(type=action_type, data=data, depends_on=depends_list)

    @staticmethod
    def _attach_plan_dir(plan: Plan, base_dir: Path) -> None:
        base = str(base_dir)
        for task in plan.tasks:
            for action in task.actions:
                action.data.setdefault("_plan_dir", base)

    def _read_with_includes(self, path: Path, seen: set[Path] | None = None) -> str:
        seen = seen or set()
        real = path.resolve()
        if real in seen:
            raise ValueError(f"Recursive include detected for {path}")
        seen.add(real)
        lines: list[str] = []
        for line in path.read_text().splitlines():
            stripped = line.strip()
            match = self.INCLUDE_RE.match(stripped)
            if match:
                include_path = (path.parent / match.group(1)).resolve()
                lines.append(self._read_with_includes(include_path, seen))
            else:
                lines.append(line)
        return "\n".join(lines)
