"""Resource identities depend on managed targets, never task position or source paths."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from .types import ActionSpec


def resource_id(action: ActionSpec) -> str:
    spec = action.data
    if action.type == "authorized_key":
        from .operations.authorized_key import AuthorizedKeyOperation
        target = [spec.get("user"), sorted(AuthorizedKeyOperation._split_keys(
            AuthorizedKeyOperation._normalize_key(str(spec.get("key", "")))))]
    elif action.type == "cron":
        target = [spec.get("target", "cron_d"), spec.get("user", "root"), spec.get("name")]
    elif action.type == "package" and not spec.get("name"):
        target = sorted(set(spec.get("packages", [])))
    else:
        target = next((spec[k] for k in ("path", "dest", "mount_point", "name", "user", "service") if spec.get(k)), None)
        if isinstance(target, str):
            return f"{action.type}.{target}"
        if target is None:
            target = {k: v for k, v in spec.items() if not k.startswith("_") and k != "state"}
    digest = hashlib.sha256(json.dumps(target, sort_keys=True, default=str).encode()).hexdigest()
    return f"{action.type}.{digest}"


def state_actions(action: ActionSpec):
    """Track bulk package resources individually so edits only remove deleted members."""
    specs = [action.data]
    if action.type == "package" and not action.data.get("name"):
        specs = [{**action.data, "name": name} for name in dict.fromkeys(action.data.get("packages", []))]
    if action.type == "authorized_key":
        from .operations.authorized_key import AuthorizedKeyOperation
        keys = AuthorizedKeyOperation._split_keys(AuthorizedKeyOperation._normalize_key(str(action.data.get("key", ""))))
        specs = [{**action.data, "key": key} for key in keys]
    for spec in specs:
        data = dict(spec)
        if action.type == "package":
            data.pop("packages", None)
        item = replace(action, data=data)
        data["_resource_id"] = resource_id(item)
        yield item


def plan_actions(plan):
    def walk(actions):
        for action in actions:
            yield action
            yield from walk(action.on_success)
            yield from walk(action.on_failure)
    for task in plan.tasks:
        for host in task.hosts:
            for action in walk(task.actions):
                yield host, action
