# Writing custom plugins

Geppetto can load external Python modules to add new operations without patching the core. Plugins register their operations with the global registry before a plan runs.

## Plugin contract

- Export a function `register_operations(registry)` that mutates the provided dict (usually `OPERATION_REGISTRY`).
- Provide `Operation` subclasses implementing `apply(self, host, executor) -> ActionResult`.
- Keep names unique (the registry key becomes the action type used in plans).

Example module:

```python
from geppetto_automation.operations.base import Operation
from geppetto_automation.types import ActionResult, HostConfig

class SayHello(Operation):
    def __init__(self, spec: dict):
        super().__init__(spec)
        self.message = spec.get("message", "hello")

    def apply(self, host: HostConfig, executor) -> ActionResult:
        return ActionResult(host=host.name, action="say_hello", changed=False,
                           details=f"greeting: {self.message}")

def register_operations(registry):
    registry["say_hello"] = SayHello
```

You can test it by dropping the file under `examples/plugins/` and pointing `plugin_dirs` at that path. The repository already ships `examples/plugins/custom_ops.py` as a minimal reference.

## How Geppetto loads plugins

The CLI reads `plugin_modules` and `plugin_dirs` from `main.conf`:

```toml
[defaults]
plugin_modules = ["yourpackage.geppetto_plugins"]
plugin_dirs = ["/etc/geppetto/plugins"]
```

For each module in `plugin_modules`, Geppetto runs `importlib.import_module` and calls `register_operations` if present.

For each `*.py` file in `plugin_dirs`, Geppetto loads it directly and calls `register_operations` if present.

Any exception during import stops the run; check stderr for the failure. Logging at INFO will show which plugins loaded.

## Packaging and dependencies

- Ship your plugin as a normal Python package and ensure it is installed alongside `geppetto-automation`, or drop standalone `.py` files into a plugin directory.
- If your operation needs extra dependencies, declare them in your package. For standalone files, install the deps system-wide or vendor them.
- Avoid side effects on import; keep all work inside `register_operations` or `apply`.
- Looking for ready-made plugins? Browse https://github.com/daveseff/Geppetto_Plugins.

## Writing robust operations

- Validate input in `__init__` and raise `ValueError` with clear messages.
- Keep `apply` idempotent and return meaningful `ActionResult.details`.
- Use existing executors for commands/files where possible; avoid shelling out unless needed.
- Names should be lowercase with underscores (e.g., `my_op`) to match DSL style.

## Quick usage test

1. Create `~/geppetto-plugins/hello.py` with the example above.
2. Add `plugin_dirs = ["/home/you/geppetto-plugins"]` to `main.conf`.
3. Add to a plan:

   ```
   say_hello { 'demo':
     message => 'hi from plugin'
   }
   ```

4. Run `geppetto-auto /path/to/plan.fops --dry-run` and verify the `say_hello` action logs `greeting: hi from plugin`.

If you prefer packaging, publish a module and list it under `plugin_modules`; Geppetto will import it just like any other installed Python package.
