from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union
import os
import shutil
import stat
import subprocess

from .types import HostConfig


@dataclass
class CommandResult:
    command: list[str]
    stdout: str
    stderr: str
    returncode: int


class Executor:
    """Base executor abstraction used by operations."""

    def __init__(self, host: HostConfig, *, dry_run: bool = False):
        self.host = host
        self.dry_run = dry_run

    def run(
        self,
        command: Sequence[str],
        *,
        check: bool = True,
        mutable: bool = True,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        """Run ``command`` and optionally skip it during dry-runs."""

        cmd_list = list(command)
        if self.dry_run and mutable:
            return CommandResult(cmd_list, "", "skipped (dry-run)", 0)

        exec_env = None
        if env:
            exec_env = os.environ.copy()
            exec_env.update(env)

        proc = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            check=False,
            env=exec_env,
            cwd=str(cwd) if cwd is not None else None,
            timeout=timeout,
        )
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode,
                cmd_list,
                proc.stdout,
                proc.stderr,
            )
        return CommandResult(cmd_list, proc.stdout, proc.stderr, proc.returncode)

    # File primitives -----------------------------------------------------
    def read_file(self, path: Path) -> Optional[str]:
        raise NotImplementedError

    def write_file(self, path: Path, *, content: str, mode: Optional[int]) -> tuple[bool, str]:
        raise NotImplementedError

    def ensure_directory(self, path: Path, *, mode: Optional[int]) -> tuple[bool, str]:
        raise NotImplementedError

    def remove_path(self, path: Path) -> bool:
        raise NotImplementedError


class LocalExecutor(Executor):
    """Executor that acts directly on the local host."""

    def read_file(self, path: Path) -> Optional[str]:
        try:
            return path.read_text()
        except FileNotFoundError:
            return None

    def write_file(self, path: Path, *, content: str, mode: Optional[int]) -> tuple[bool, str]:
        current = self.read_file(path)
        changed = False
        reasons: list[str] = []

        if current != content:
            changed = True
            reasons.append("content")
            if not self.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

        if mode is not None:
            existing_mode = self._file_mode(path)
            if existing_mode != mode:
                changed = True
                reasons.append(f"mode->{mode:04o}")
                if not self.dry_run:
                    # ``chmod`` fails if the file is absent, so guard it.
                    if path.exists():
                        os.chmod(path, mode)
        detail = ", ".join(reasons) if reasons else "noop"
        return changed, detail

    def ensure_directory(self, path: Path, *, mode: Optional[int]) -> tuple[bool, str]:  # type: ignore[override]
        changed = False
        reasons: list[str] = []

        if not path.exists():
            changed = True
            reasons.append("created")
            if not self.dry_run:
                path.mkdir(parents=True, exist_ok=True)
        elif not path.is_dir():
            changed = True
            reasons.append("replaced-non-dir")
            if not self.dry_run:
                self.remove_path(path)
                path.mkdir(parents=True, exist_ok=True)

        if mode is not None:
            existing_mode = self._file_mode(path)
            if existing_mode != mode:
                changed = True
                reasons.append(f"mode->{mode:04o}")
                if not self.dry_run:
                    # ``chmod`` fails if the path is absent, so guard it.
                    if path.exists():
                        os.chmod(path, mode)
        detail = ", ".join(reasons) if reasons else "noop"
        return changed, detail

    def remove_path(self, path: Path) -> bool:
        if not path.exists():
            return False
        if self.dry_run:
            return True
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True

    @staticmethod
    def _file_mode(path: Path) -> Optional[int]:
        try:
            return stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            return None


class AgentExecutor(Executor):
    """Placeholder for a daemon/agent backed executor."""

    def run(self, command: Sequence[str], *, check: bool = True, mutable: bool = True) -> CommandResult:  # type: ignore[override]
        raise NotImplementedError("AgentExecutor is not implemented yet")

    def read_file(self, path: Path) -> Optional[str]:  # type: ignore[override]
        raise NotImplementedError

    def write_file(self, path: Path, *, content: str, mode: Optional[int]) -> tuple[bool, str]:  # type: ignore[override]
        raise NotImplementedError

    def ensure_directory(self, path: Path, *, mode: Optional[int]) -> tuple[bool, str]:  # type: ignore[override]
        raise NotImplementedError

    def remove_path(self, path: Path) -> bool:  # type: ignore[override]
        raise NotImplementedError
