from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HostConfig:
    name: str
    connection: str = "local"
    address: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionSpec:
    type: str
    data: dict[str, Any]


@dataclass
class TaskSpec:
    name: str
    hosts: list[str]
    actions: list[ActionSpec]


@dataclass
class Plan:
    hosts: dict[str, HostConfig]
    tasks: list[TaskSpec]


@dataclass
class ActionResult:
    host: str
    action: str
    changed: bool
    details: str
