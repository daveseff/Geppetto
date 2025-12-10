from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class HostConfig:
    name: str
    connection: str = "local"
    address: Optional[str] = None
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionSpec:
    type: str
    data: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    on_success: list["ActionSpec"] = field(default_factory=list)
    on_failure: list["ActionSpec"] = field(default_factory=list)


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
    failed: bool = False
    resource: Optional[str] = None
