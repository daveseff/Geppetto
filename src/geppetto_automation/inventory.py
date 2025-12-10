from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import re

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

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
            snippet = ""
            try:
                snippet = self._line_snippet(text if "text" in locals() else path.read_text(), exc.line)
            except Exception:
                snippet = ""
            message = f"{path}:{line} {exc}"
            if snippet:
                message = f"{message} -> {snippet}"
            raise DSLParseError(message) from None
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
            actions = [
                InventoryLoader._parse_action(action, f"{index}.{pos}")
                for pos, action in enumerate(task.get("actions", []), start=1)
            ]
            tasks.append(TaskSpec(name=name, hosts=target_hosts, actions=actions))
        return tasks

    @staticmethod
    def _parse_action(action: dict[str, Any], action_index: str) -> ActionSpec:
        return InventoryLoader._parse_action_dict(action, action_index)

    @staticmethod
    def _parse_action_dict(action: dict[str, Any], action_index: str) -> ActionSpec:
        action_type = action.get("type")
        if not action_type:
            raise ValueError(f"Action {action_index} is missing a type")
        depends = action.get("depends_on", [])
        if isinstance(depends, str):
            depends_list = [depends]
        else:
            depends_list = list(depends or [])
        on_success = InventoryLoader._parse_nested_actions(action.get("on_success", []), f"{action_index}.s")
        on_failure = InventoryLoader._parse_nested_actions(action.get("on_failure", []), f"{action_index}.f")
        data = {k: v for k, v in action.items() if k not in {"type", "depends_on", "on_success", "on_failure"}}
        return ActionSpec(
            type=action_type,
            data=data,
            depends_on=depends_list,
            on_success=on_success,
            on_failure=on_failure,
        )

    @staticmethod
    def _parse_nested_actions(value: Any, action_index: str) -> list[ActionSpec]:
        if not value:
            return []
        items = value if isinstance(value, list) else [value]
        actions: list[ActionSpec] = []
        for idx, raw in enumerate(items, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"Action {action_index}.{idx} nested action must be a mapping")
            actions.append(InventoryLoader._parse_action_dict(raw, f"{action_index}.{idx}"))
        return actions

    @staticmethod
    def _attach_plan_dir(plan: Plan, base_dir: Path) -> None:
        base = str(base_dir)

        def _assign(action: ActionSpec) -> None:
            action.data.setdefault("_plan_dir", base)
            for child in action.on_success:
                _assign(child)
            for child in action.on_failure:
                _assign(child)

        for task in plan.tasks:
            for action in task.actions:
                _assign(action)

    def _read_with_includes(self, path: Path, seen: Optional[set[Path]] = None) -> str:
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

    @staticmethod
    def _line_snippet(text: str, line_number: Optional[int]) -> str:
        if line_number is None:
            return ""
        lines = text.splitlines()
        idx = line_number - 1
        if 0 <= idx < len(lines):
            return lines[idx].strip()
        return ""
