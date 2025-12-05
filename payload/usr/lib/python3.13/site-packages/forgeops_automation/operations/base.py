from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..types import ActionResult, HostConfig
from ..executors import Executor


class Operation(ABC):
    """Shared surface for runnable automation actions."""

    def __init__(self, spec: dict[str, Any]):
        self.spec = spec

    @abstractmethod
    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        """Perform the operation against ``host`` using ``executor``."""
