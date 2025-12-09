from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional
import os

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


class RemoteFetcher:
    def __init__(self, executor: Executor):
        self.executor = executor

    def fetch(self, source: str) -> Path:
        tmp_fd, tmp_name = tempfile.mkstemp(prefix="forgeops-fetch-")
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        if source.startswith("s3://"):
            self.executor.run(["aws", "s3", "cp", source, str(tmp_path)])
        elif source.startswith(("http://", "https://")):
            self.executor.run(["curl", "-fsSL", source, "-o", str(tmp_path)])
        elif source.startswith("file://"):
            shutil.copyfile(Path(source[7:]), tmp_path)
        else:
            local = Path(source)
            if not local.exists():
                raise FileNotFoundError(f"Source {source} not found")
            shutil.copyfile(local, tmp_path)
        return tmp_path

    @staticmethod
    def cleanup(path: Path) -> None:
        path.unlink(missing_ok=True)


class RemoteFileOperation(Operation):
    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        self.source = spec.get("source")
        if not self.source:
            raise ValueError("remote_file requires a source")
        raw_dest = spec.get("dest") or spec.get("path")
        if not raw_dest:
            raise ValueError("remote_file requires a dest/path")
        self.dest = Path(str(raw_dest))
        self.mode = self._parse_mode(spec.get("mode"))
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("remote_file state must be 'present' or 'absent'")
        checksum = spec.get("checksum")
        self.checksum_algo: Optional[str] = None
        self.checksum_value: Optional[str] = None
        if checksum:
            text = str(checksum)
            if ":" in text:
                algo, value = text.split(":", 1)
                self.checksum_algo = algo.lower()
                self.checksum_value = value.strip().lower()
            else:
                self.checksum_algo = "sha256"
                self.checksum_value = text.strip().lower()

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self.state == "absent":
            if not self.dest.exists():
                return ActionResult(host=host.name, action="remote_file", changed=False, details="noop")
            if not executor.dry_run:
                self.dest.unlink()
            return ActionResult(host=host.name, action="remote_file", changed=True, details="removed")

        fetcher = RemoteFetcher(executor)
        tmp = fetcher.fetch(str(self.source))
        try:
            new_bytes = tmp.read_bytes()
            if self.checksum_algo and self.checksum_value:
                digest = hashlib.new(self.checksum_algo)
                digest.update(new_bytes)
                if digest.hexdigest().lower() != self.checksum_value:
                    raise ValueError("Checksum mismatch for remote_file")
            changed = True
            if self.dest.exists():
                existing = self.dest.read_bytes()
                changed = existing != new_bytes
            detail = "updated" if changed else "noop"
            if changed and not executor.dry_run:
                self.dest.parent.mkdir(parents=True, exist_ok=True)
                self.dest.write_bytes(new_bytes)
                if self.mode is not None:
                    self.dest.chmod(self.mode)
            return ActionResult(host=host.name, action="remote_file", changed=changed, details=detail)
        finally:
            RemoteFetcher.cleanup(tmp)

    @staticmethod
    def _parse_mode(value: Optional[Any]) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        base = 8 if text.startswith("0") else 10
        return int(text, base)


class RpmInstallOperation(Operation):
    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name")
        if not raw_name:
            raise ValueError("rpm operation requires a name")
        self.name = str(raw_name)
        raw_source = spec.get("source")
        if not raw_source:
            raise ValueError("rpm operation requires a source")
        self.source = str(raw_source)
        self.allow_downgrade = bool(spec.get("allow_downgrade", False))
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("rpm state must be 'present' or 'absent'")

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        query = executor.run(["rpm", "-q", self.name], check=False, mutable=False)
        installed = query.returncode == 0

        if self.state == "absent":
            if not installed:
                return ActionResult(host=host.name, action="rpm", changed=False, details="noop")
            executor.run(["rpm", "-e", self.name])
            return ActionResult(host=host.name, action="rpm", changed=True, details="removed")

        if installed:
            return ActionResult(host=host.name, action="rpm", changed=False, details="already-installed")

        fetcher = RemoteFetcher(executor)
        tmp = fetcher.fetch(self.source)
        try:
            cmd = ["rpm", "-Uvh", str(tmp)]
            if self.allow_downgrade:
                cmd.insert(1, "--oldpackage")
            executor.run(cmd)
            return ActionResult(host=host.name, action="rpm", changed=True, details="installed")
        finally:
            RemoteFetcher.cleanup(tmp)
