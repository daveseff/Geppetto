import sys
from pathlib import Path

import geppetto_automation.operations as ops
from geppetto_automation import cli
from geppetto_automation.cli import _load_plugins
from geppetto_automation.config import GeppettoConfig
from geppetto_automation.operations.base import Operation
from geppetto_automation.types import ActionResult, HostConfig


def test_plugin_module_registration(monkeypatch, tmp_path: Path):
    plugin_dir = tmp_path / "mods"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "custom_op.py"
    plugin_file.write_text(
        """
from geppetto_automation.operations.base import Operation
from geppetto_automation.types import ActionResult, HostConfig

class CustomOp(Operation):
    def apply(self, host: HostConfig, executor) -> ActionResult:
        return ActionResult(host=host.name, action="custom_op", changed=False, details="noop")

def register_operations(registry):
    registry["custom_op"] = CustomOp
"""
    )

    cfg = GeppettoConfig(plugin_dirs=[plugin_dir])
    registry: dict = {}
    # Ensure a clean registry slot for the test
    monkeypatch.setattr(ops, "OPERATION_REGISTRY", registry)
    monkeypatch.setattr(cli, "OPERATION_REGISTRY", registry)
    _load_plugins(cfg)

    assert "custom_op" in ops.OPERATION_REGISTRY
    assert issubclass(ops.OPERATION_REGISTRY["custom_op"], Operation)


def test_plugin_module_import(monkeypatch, tmp_path: Path):
    # Create a real importable module
    mod_path = tmp_path / "myplugin"
    mod_path.mkdir()
    (mod_path / "__init__.py").write_text("")
    module_file = mod_path / "extra_ops.py"
    module_file.write_text(
        """
from geppetto_automation.operations.base import Operation
from geppetto_automation.types import ActionResult, HostConfig

class ExtraOp(Operation):
    def apply(self, host: HostConfig, executor) -> ActionResult:
        return ActionResult(host=host.name, action="extra_op", changed=False, details="noop")

def register_operations(registry):
    registry["extra_op"] = ExtraOp
"""
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    cfg = GeppettoConfig(plugin_modules=["myplugin.extra_ops"])
    registry: dict = {}
    monkeypatch.setattr(ops, "OPERATION_REGISTRY", registry)
    monkeypatch.setattr(cli, "OPERATION_REGISTRY", registry)

    _load_plugins(cfg)

    assert "extra_op" in ops.OPERATION_REGISTRY
    assert issubclass(ops.OPERATION_REGISTRY["extra_op"], Operation)
