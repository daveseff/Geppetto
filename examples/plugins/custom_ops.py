"""
Example plugin module for Geppetto.

Drop this file into a plugin directory (see plugin_dirs in main.conf) or make it
importable (plugin_modules) and it will register a new operation called
`say_hello` that prints a greeting without making system changes.
"""

from geppetto_automation.operations.base import Operation
from geppetto_automation.types import ActionResult, HostConfig


class SayHelloOperation(Operation):
    def __init__(self, spec: dict):
        super().__init__(spec)
        self.message = spec.get("message", "hello")

    def apply(self, host: HostConfig, executor) -> ActionResult:
        detail = f"greeting: {self.message}"
        # no system changes, so changed=False
        return ActionResult(host=host.name, action="say_hello", changed=False, details=detail)


def register_operations(registry) -> None:
    registry["say_hello"] = SayHelloOperation
