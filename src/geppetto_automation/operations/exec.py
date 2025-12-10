from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional, Sequence
from string import Template
import logging

from .base import Operation
from ..executors import CommandResult, Executor
from ..secrets import SecretResolver
from ..types import ActionResult, HostConfig

logger = logging.getLogger(__name__)


class ExecOperation(Operation):
    """Run arbitrary commands with simple guards, mirroring Puppet's exec."""

    secret_resolver = SecretResolver()

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name")
        if not raw_name:
            raise ValueError("exec operation requires a name")
        self.name = str(raw_name)

        raw_command = spec.get("command") or spec.get("cmd")
        if raw_command is None:
            raise ValueError("exec operation requires a command")
        self.raw_command = raw_command

        self.only_if = spec.get("only_if")
        self.unless = spec.get("unless")

        self.creates = Path(str(spec["creates"])) if "creates" in spec else None
        self.cwd = Path(str(spec["cwd"])) if "cwd" in spec else None

        self.env = self._normalize_env(spec.get("env") or spec.get("environment"))
        raw_vars = spec.get("variables", {})
        if raw_vars is not None and not isinstance(raw_vars, dict):
            raise ValueError("exec variables must be a mapping")
        self.variables = dict(raw_vars or {})

        returns = spec.get("returns", [0])
        self.allowed_returns = self._normalize_returns(returns)
        self.timeout = self._normalize_timeout(spec.get("timeout"))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        context = self.secret_resolver.resolve({**host.variables, **self.variables})
        command = self._render_and_normalize(self.raw_command, context)

        if self.creates:
            creates_path = self._resolve_path(self.creates)
            if creates_path.exists():
                detail = f"skipped (creates {creates_path})"
                return ActionResult(host=host.name, action="exec", changed=False, details=detail)

        if self.only_if:
            guard_cmd = self._render_and_normalize(self.only_if, context)
            guard = self._run_guard(guard_cmd, executor)
            if guard.returncode != 0:
                detail = f"skipped (only_if rc={guard.returncode})"
                return ActionResult(host=host.name, action="exec", changed=False, details=detail)

        if self.unless:
            guard_cmd = self._render_and_normalize(self.unless, context)
            guard = self._run_guard(guard_cmd, executor)
            if guard.returncode == 0:
                detail = f"skipped (unless rc={guard.returncode})"
                return ActionResult(host=host.name, action="exec", changed=False, details=detail)

        result = executor.run(
            command,
            check=False,
            mutable=True,
            env=self.env,
            cwd=self.cwd,
            timeout=self.timeout,
        )

        if result.returncode not in self.allowed_returns:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "exec failed name=%s rc=%s cmd=%s",
                    self.name,
                    result.returncode,
                    self._format_command(command),
                )
            detail = self._error_detail(result)
            return ActionResult(
                host=host.name,
                action="exec",
                changed=False,
                details=detail,
                failed=True,
            )

        detail = "dry-run" if executor.dry_run else f"ran (rc={result.returncode})"
        return ActionResult(host=host.name, action="exec", changed=True, details=detail)

    def _run_guard(self, command: Sequence[str], executor: Executor) -> CommandResult:
        return executor.run(
            command,
            check=False,
            mutable=False,
            env=self.env,
            cwd=self.cwd,
            timeout=self.timeout,
        )

    def _render_and_normalize(self, value: Any, context: dict[str, Any]) -> list[str]:
        if isinstance(value, str):
            rendered = Template(value).safe_substitute(context)
            return self._normalize_command(rendered)
        if isinstance(value, Sequence):
            rendered = [Template(str(v)).safe_substitute(context) for v in value]
            return self._normalize_command(rendered)
        raise ValueError("exec command/guard must be a string or list")

    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute() or self.cwd is None:
            return path
        return self.cwd / path

    @staticmethod
    def _normalize_command(value: Any) -> list[str]:
        if isinstance(value, str):
            return ["sh", "-c", value]
        if isinstance(value, Sequence):
            return [str(v) for v in value]
        raise ValueError("exec command must be a string or list")

    @staticmethod
    def _format_command(command: Sequence[str]) -> str:
        return " ".join(command)

    @staticmethod
    def _normalize_env(value: Any) -> Optional[dict[str, str]]:
        if value is None:
            return None
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            env: dict[str, str] = {}
            for item in value:
                key, sep, val = str(item).partition("=")
                if not sep:
                    raise ValueError("env list entries must be KEY=VALUE")
                env[key] = val
            return env
        raise ValueError("exec env must be a mapping or list of KEY=VALUE strings")

    @staticmethod
    def _normalize_returns(value: Any) -> list[int]:
        if value is None:
            return [0]
        if isinstance(value, int):
            return [int(value)]
        if isinstance(value, Iterable):
            return [int(v) for v in value]
        raise ValueError("exec returns must be an int or list of ints")

    @staticmethod
    def _normalize_timeout(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:  # noqa: PERF203
            raise ValueError("exec timeout must be numeric") from exc

    @staticmethod
    def _error_detail(result: CommandResult) -> str:
        message = ExecOperation._summarize_output(result)
        prefix = f"rc={result.returncode}"
        if message:
            return f"{prefix}: {message}"
        return prefix

    @staticmethod
    def _summarize_output(result: CommandResult) -> Optional[str]:
        for text in (result.stderr, result.stdout):
            if not text:
                continue
            stripped = text.strip()
            if not stripped:
                continue
            line = stripped.splitlines()[0]
            return (line[:157] + "...") if len(line) > 160 else line
        return None
