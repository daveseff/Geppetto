from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional
import os

from .operations import OPERATION_REGISTRY
from .types import ActionResult, HostConfig

logger = logging.getLogger(__name__)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _destroy_file(spec: dict[str, Any]) -> dict[str, Any]:
    new_spec = dict(spec)
    new_spec["state"] = "absent"
    return new_spec


DESTROY_BUILDERS: dict[str, Callable[[dict[str, Any]], Optional[dict[str, Any]]]] = {
    "file": _destroy_file,
    "remote_file": _destroy_file,
    "user": lambda spec: {**spec, "state": "absent"},
    "authorized_key": lambda spec: {**spec, "state": "absent"},
    "ca_cert": lambda spec: {**spec, "state": "absent"},
    "service": lambda spec: {**spec, "enabled": False, "state": "stopped"},
    "efs_mount": lambda spec: {**spec, "state": "absent"},
    "network_mount": lambda spec: {**spec, "state": "absent"},
    "block_device": lambda spec: {**spec, "state": "absent", "mount": True},
    "rpm": lambda spec: {**spec, "state": "absent"},
    "package": lambda spec: {**spec, "state": "absent"},
    "timezone": lambda spec: {**spec, "state": "absent"},
    "sysctl": lambda spec: {**spec, "state": "absent"},
    "cron": lambda spec: {**spec, "state": "absent"},
}


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.previous = self._load()
        self.current: dict[str, dict[str, dict[str, Any]]] = {}

    def record(self, host: str, action) -> None:
        if action.type not in DESTROY_BUILDERS:
            return
        spec = _normalize_value(action.data)
        resource_id = spec.get("_resource_id")
        key = resource_id or self._make_key(action.type, spec)
        entry = {
            "action": action.type,
            "spec": spec,
            "resource_id": resource_id,
            "depends_on": list(action.depends_on),
        }
        self.current.setdefault(host, {})[key] = entry

    def finalize(self, plan, executor_factory) -> list[ActionResult]:
        results: list[ActionResult] = []
        for host_name, entries in list(self.previous.items()):
            host = plan.hosts.get(host_name)
            if not host:
                logger.debug("Skipping cleanup for unknown host %s", host_name)
                continue
            ordered_keys = self._order_entries(entries, reverse=True)
            for key in ordered_keys:
                if key in self.current.get(host_name, {}):
                    continue
                entry = entries[key]
                result = self._destroy_entry(host, entry, executor_factory)
                if result is not None:
                    results.append(result)
        self._write()
        return results

    def _destroy_entry(self, host: HostConfig, entry: dict[str, Any], executor_factory) -> Optional[ActionResult]:
        action_type = entry.get("action")
        builder = DESTROY_BUILDERS.get(action_type)
        if not builder:
            return None
        spec = builder(dict(entry.get("spec", {})))
        operation_cls = OPERATION_REGISTRY.get(action_type)
        if not operation_cls:
            logger.warning("No operation registered for '%s' when cleaning up", action_type)
            return None
        executor = executor_factory(host)
        operation = operation_cls(spec)
        try:
            return operation.apply(host, executor)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to clean up %s on host %s: %s", action_type, host.name, exc)
            return ActionResult(
                host=host.name,
                action=action_type or "unknown",
                changed=False,
                details=str(exc),
                failed=True,
            )

    def _write(self) -> None:
        data = self.current
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            logger.debug("Unable to chmod state file %s", self.path, exc_info=True)
        self.previous = data

    def _load(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            logger.warning("State file %s is corrupt; starting fresh", self.path)
            return {}

    def _make_key(self, action_type: str, spec: dict[str, Any]) -> str:
        normalized = _normalize_value(spec)
        payload = json.dumps({"action": action_type, "spec": normalized}, sort_keys=True)
        return payload

    def _order_entries(self, entries: dict[str, dict[str, Any]], reverse: bool = False) -> list[str]:
        if not entries:
            return []
        id_to_key: dict[str, str] = {}
        for key, entry in entries.items():
            rid = entry.get("resource_id") or key
            id_to_key[rid] = key

        deps_map: dict[str, set[str]] = {}
        in_degree: dict[str, int] = {}
        for key, entry in entries.items():
            rid = entry.get("resource_id") or key
            deps = {dep for dep in entry.get("depends_on", []) if dep in id_to_key}
            deps_map[rid] = deps
            in_degree[rid] = len(deps)
        queue = [rid for rid, deg in in_degree.items() if deg == 0]
        ordered: list[str] = []
        while queue:
            current = queue.pop(0)
            ordered.append(current)
            for node, deps in deps_map.items():
                if current in deps:
                    in_degree[node] -= 1
                    if in_degree[node] == 0:
                        queue.append(node)
        for rid in deps_map:
            if rid not in ordered:
                ordered.append(rid)
        if reverse:
            ordered.reverse()
        return [id_to_key.get(rid, rid) for rid in ordered]
