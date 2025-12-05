from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from .operations import OPERATION_REGISTRY

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


DESTROY_BUILDERS: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {
    "file": _destroy_file,
    "remote_file": _destroy_file,
    "user": lambda spec: {**spec, "state": "absent"},
    "authorized_key": lambda spec: {**spec, "state": "absent"},
    "service": lambda spec: {**spec, "enabled": False, "state": "stopped"},
    "efs_mount": lambda spec: {**spec, "state": "absent"},
    "network_mount": lambda spec: {**spec, "state": "absent"},
    "block_device": lambda spec: {**spec, "state": "absent", "mount": True},
    "rpm": lambda spec: {**spec, "state": "absent"},
}


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.previous = self._load()
        self.current: dict[str, dict[str, dict[str, Any]]] = {}

    def record(self, host: str, action_type: str, spec: dict[str, Any]) -> None:
        if action_type not in DESTROY_BUILDERS:
            return
        key = self._make_key(action_type, spec)
        normalized = _normalize_value(spec)
        self.current.setdefault(host, {})[key] = {"action": action_type, "spec": normalized}

    def finalize(self, plan, executor_factory) -> None:
        for host_name, entries in list(self.previous.items()):
            host = plan.hosts.get(host_name)
            if not host:
                logger.debug("Skipping cleanup for unknown host %s", host_name)
                continue
            for key, entry in list(entries.items()):
                if key in self.current.get(host_name, {}):
                    continue
                self._destroy_entry(host, entry, executor_factory)
        self._write()

    def _destroy_entry(self, host, entry: dict[str, Any], executor_factory) -> None:
        action_type = entry.get("action")
        builder = DESTROY_BUILDERS.get(action_type)
        if not builder:
            return
        spec = builder(dict(entry.get("spec", {})))
        operation_cls = OPERATION_REGISTRY.get(action_type)
        if not operation_cls:
            logger.warning("No operation registered for '%s' when cleaning up", action_type)
            return
        executor = executor_factory(host)
        operation = operation_cls(spec)
        try:
            operation.apply(host, executor)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to clean up %s on host %s: %s", action_type, host.name, exc)

    def _write(self) -> None:
        data = self.current
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))
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
