from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional
import time

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig


def _normalize_mount_options(options: Any, default: str) -> str:
    if isinstance(options, str):
        return options or default
    if isinstance(options, (list, tuple, set)):
        return ",".join(str(opt) for opt in options)
    return str(options)


def _coerce_bool(value: Optional[Any], default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
    return bool(value)


class FstabManager:
    def __init__(self, path: Path):
        self.path = path

    def ensure_entry(self, mount_point: str, record: str) -> bool:
        lines = self._read_lines()
        changed = False
        replaced = False
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            parts = stripped.split()
            if len(parts) >= 2 and parts[1] == mount_point:
                replaced = True
                if stripped != record:
                    new_lines.append(record)
                    changed = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(record)
            changed = True
        if changed:
            self._write_lines(new_lines)
        return changed

    def remove_entry(self, mount_point: str) -> bool:
        lines = self._read_lines()
        new_lines: list[str] = []
        removed = False
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            parts = stripped.split()
            if len(parts) >= 2 and parts[1] == mount_point:
                removed = True
                continue
            new_lines.append(line)
        if removed:
            self._write_lines(new_lines)
        return removed

    def _read_lines(self) -> list[str]:
        try:
            return self.path.read_text().splitlines()
        except FileNotFoundError:
            return []

    def _write_lines(self, lines: Iterable[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(lines)
        if text:
            text += "\n"
        self.path.write_text(text)


class MountMixin:
    def _is_mounted(self, executor: Executor, mount_point: str) -> bool:
        result = executor.run(["mountpoint", "-q", mount_point], check=False, mutable=False)
        return result.returncode == 0

    def _mount(self, executor: Executor, mount_point: str) -> None:
        executor.run(["mount", mount_point])

    def _unmount(self, executor: Executor, mount_point: str) -> None:
        executor.run(["umount", mount_point])


class NetworkMountOperation(Operation, MountMixin):
    """Ensure a generic network filesystem is mounted via /etc/fstab."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_source = spec.get("source")
        if not raw_source:
            raise ValueError("network_mount requires a source")
        self.source = str(raw_source)
        raw_mount = spec.get("mount_point")
        if not raw_mount:
            raise ValueError("network_mount requires a mount_point")
        self.mount_point = str(raw_mount)
        if not self.mount_point.startswith("/"):
            raise ValueError("mount_point must be absolute")
        self.fstype = str(spec.get("fstype", spec.get("filesystem", "nfs")))
        self.options = _normalize_mount_options(spec.get("mount_options", spec.get("options", "defaults")), "defaults")
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("network_mount state must be 'present' or 'absent'")
        self.ensure_mounted = bool(_coerce_bool(spec.get("mount", True), True))
        self.fstab_path = Path(spec.get("fstab", "/etc/fstab"))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        mount_dir = Path(self.mount_point)
        fstab = FstabManager(self.fstab_path)
        changes: list[str] = []
        record = f"{self.source} {self.mount_point} {self.fstype} {self.options} 0 0"

        if self.state == "present":
            if not mount_dir.exists():
                mount_dir.mkdir(parents=True, exist_ok=True)
            if fstab.ensure_entry(self.mount_point, record):
                changes.append("fstab")
            if self.ensure_mounted and not self._is_mounted(executor, self.mount_point):
                self._mount(executor, self.mount_point)
                changes.append("mounted")
        else:
            if fstab.remove_entry(self.mount_point):
                changes.append("fstab-removed")
            if self.ensure_mounted and self._is_mounted(executor, self.mount_point):
                self._unmount(executor, self.mount_point)
                changes.append("unmounted")

        detail = ", ".join(changes) if changes else "noop"
        return ActionResult(host=host.name, action="network_mount", changed=bool(changes), details=detail)


class EfsMountOperation(NetworkMountOperation):
    """Wrapper around network mounts that derives the EFS source."""

    def __init__(self, spec: dict[str, Any]):
        filesystem_id = spec.get("filesystem_id")
        if not filesystem_id:
            raise ValueError("efs_mount requires a filesystem_id")
        derived = dict(spec)
        derived.setdefault("source", f"{filesystem_id}:/")
        derived.setdefault("fstype", "efs")
        derived.setdefault("mount_options", spec.get("mount_options", "tls,_netdev"))
        super().__init__(derived)


class BlockDeviceMountOperation(Operation, MountMixin):
    """Ensure a block device is formatted and mounted by UUID."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_device = spec.get("device")
        self.device_path = Path(str(raw_device)) if raw_device else None
        raw_mount = spec.get("mount_point")
        if not raw_mount:
            raise ValueError("block_device operation requires a mount_point")
        self.mount_point = str(raw_mount)
        if not self.mount_point.startswith("/"):
            raise ValueError("mount_point must be absolute")
        self.filesystem = str(spec.get("filesystem", "xfs"))
        self.options = _normalize_mount_options(spec.get("mount_options", "defaults"), "defaults")
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("block_device state must be 'present' or 'absent'")
        self.mkfs = bool(_coerce_bool(spec.get("mkfs", True), True))
        self.ensure_mounted = bool(_coerce_bool(spec.get("mount", True), True))
        self.fstab_path = Path(spec.get("fstab", "/etc/fstab"))
        self.volume_id = spec.get("volume_id")
        self.device_hint = spec.get("device_name")
        if not any([self.device_path, self.volume_id, self.device_hint]):
            raise ValueError("block_device requires 'device', 'volume_id', or 'device_name'")
        self.wait_attempts = int(spec.get("wait_attempts", 60))
        self.wait_interval = int(spec.get("wait_interval", 5))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        fstab = FstabManager(self.fstab_path)
        mount_dir = Path(self.mount_point)
        changes: list[str] = []

        if self.state == "present":
            device_path = self._resolve_device(executor)
            if not device_path.exists():
                raise FileNotFoundError(f"Device {device_path} does not exist")
            current_fs = self._detect_filesystem(executor, device_path)
            if current_fs is None:
                if not self.mkfs:
                    raise RuntimeError(f"Device {device_path} has no filesystem and mkfs disabled")
                self._format_device(executor, device_path)
                changes.append("formatted")
            elif current_fs != self.filesystem:
                raise RuntimeError(
                    f"Device {device_path} filesystem {current_fs} does not match requested {self.filesystem}"
                )
            uuid = self._get_uuid(executor, device_path)
            record = f"UUID={uuid} {self.mount_point} {self.filesystem} {self.options} 0 2"
            mount_dir.mkdir(parents=True, exist_ok=True)
            if fstab.ensure_entry(self.mount_point, record):
                changes.append("fstab")
            if self.ensure_mounted and not self._is_mounted(executor, self.mount_point):
                self._mount(executor, self.mount_point)
                changes.append("mounted")
        else:
            if fstab.remove_entry(self.mount_point):
                changes.append("fstab-removed")
            if self.ensure_mounted and self._is_mounted(executor, self.mount_point):
                self._unmount(executor, self.mount_point)
                changes.append("unmounted")

        detail = ", ".join(changes) if changes else "noop"
        return ActionResult(host=host.name, action="block_device", changed=bool(changes), details=detail)

    def _detect_filesystem(self, executor: Executor, device: Path) -> Optional[str]:
        result = executor.run(
            ["blkid", "-o", "value", "-s", "TYPE", str(device)],
            check=False,
            mutable=False,
        )
        if result.returncode != 0:
            return None
        fs = result.stdout.strip()
        return fs or None

    def _format_device(self, executor: Executor, device: Path) -> None:
        cmd: list[str]
        dev = str(device)
        filesystem = self.filesystem.lower()
        if filesystem == "xfs":
            cmd = ["mkfs.xfs", "-f", dev]
        elif filesystem == "ext4":
            cmd = ["mkfs.ext4", "-F", dev]
        elif filesystem == "ext3":
            cmd = ["mkfs.ext3", "-F", dev]
        elif filesystem == "ext2":
            cmd = ["mkfs.ext2", dev]
        else:
            cmd = ["mkfs", "-t", self.filesystem, dev]
        executor.run(cmd)

    def _get_uuid(self, executor: Executor, device: Path) -> str:
        result = executor.run(
            ["blkid", "-o", "value", "-s", "UUID", str(device)],
            check=False,
            mutable=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Unable to determine UUID for {device}")
        uuid = result.stdout.strip()
        if not uuid:
            raise RuntimeError(f"blkid returned no UUID for {device}")
        return uuid

    def _resolve_device(self, executor: Executor) -> Path:
        if self.device_path and self.device_path.exists():
            return self.device_path
        candidates = self._candidate_paths()
        attempts = max(1, self.wait_attempts)
        for idx in range(attempts):
            for candidate in candidates:
                if candidate.exists():
                    self.device_path = candidate
                    return candidate
            if idx < attempts - 1:
                time.sleep(max(1, self.wait_interval))
        raise FileNotFoundError(
            f"Unable to locate block device for volume_id={self.volume_id} device={self.device_path}"
        )

    def _candidate_paths(self) -> list[Path]:
        candidates: list[Path] = []
        if self.device_path:
            candidates.append(self.device_path)
        if self.volume_id:
            suffix = str(self.volume_id).replace("-", "")
            candidates.extend(
                [
                    Path(f"/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_{suffix}"),
                    Path(f"/dev/disk/by-id/virtio-{suffix}"),
                ]
            )
        if self.device_hint:
            sanitized = str(self.device_hint)
            if sanitized.startswith("/dev/"):
                sanitized = sanitized[5:]
            candidates.append(Path(f"/dev/{sanitized}"))
            if sanitized.startswith("sd"):
                candidates.append(Path(f"/dev/xv{sanitized[2:]}"))
            candidates.append(Path(f"/dev/disk/by-id/virtio-{sanitized}"))
        return candidates
