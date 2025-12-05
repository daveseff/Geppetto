from pathlib import Path

from forgeops_automation.executors import CommandResult, Executor
from forgeops_automation.operations.mount import BlockDeviceMountOperation, EfsMountOperation, NetworkMountOperation
from forgeops_automation.types import HostConfig


class FakeExecutor(Executor):
    def __init__(self, responses: dict[tuple[str, ...], list[CommandResult]] | None = None):
        super().__init__(HostConfig(name="local"))
        self.responses = responses or {}
        self.commands: list[tuple[str, ...]] = []

    def run(self, command, *, check: bool = True, mutable: bool = True):  # type: ignore[override]
        key = tuple(command)
        self.commands.append(key)
        queue = self.responses.get(key)
        if queue:
            result = queue.pop(0)
            if check and result.returncode != 0:
                raise RuntimeError(f"Command failed: {' '.join(command)}")
            return result
        return CommandResult(list(command), "", "", 0)

    def read_file(self, path: Path):  # type: ignore[override]
        raise NotImplementedError

    def write_file(self, path: Path, *, content: str, mode: int | None):  # type: ignore[override]
        raise NotImplementedError

    def remove_path(self, path: Path):  # type: ignore[override]
        raise NotImplementedError


def test_efs_mount_adds_entry_and_mounts(tmp_path: Path):
    fstab = tmp_path / "fstab"
    mount_dir = tmp_path / "mnt" / "efs"
    responses = {
        ("mountpoint", "-q", str(mount_dir)): [CommandResult(["mountpoint"], "", "", 1)],
    }
    executor = FakeExecutor(responses)
    op = EfsMountOperation(
        {
            "filesystem_id": "fs-123456",
            "mount_point": str(mount_dir),
            "fstab": str(fstab),
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert "fstab" in result.details
    assert ("mount", str(mount_dir)) in executor.commands
    assert f"fs-123456:/ {mount_dir} efs tls,_netdev 0 0" in fstab.read_text()


def test_block_device_formats_and_mounts(tmp_path: Path):
    device = tmp_path / "device"
    device.touch()
    fstab = tmp_path / "fstab"
    mount_dir = tmp_path / "data"
    responses = {
        ("blkid", "-o", "value", "-s", "TYPE", str(device)): [CommandResult(["blkid"], "", "", 2)],
        ("blkid", "-o", "value", "-s", "UUID", str(device)): [
            CommandResult(["blkid"], "1111-2222\n", "", 0)
        ],
        ("mountpoint", "-q", str(mount_dir)): [CommandResult(["mountpoint"], "", "", 1)],
    }
    executor = FakeExecutor(responses)
    op = BlockDeviceMountOperation(
        {
            "device": str(device),
            "mount_point": str(mount_dir),
            "filesystem": "xfs",
            "fstab": str(fstab),
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert "formatted" in result.details
    assert ("mkfs.xfs", "-f", str(device)) in executor.commands
    assert f"UUID=1111-2222 {mount_dir} xfs defaults 0 2" in fstab.read_text()


def test_block_device_resolves_volume_id(tmp_path: Path, monkeypatch):
    mount_dir = tmp_path / "data"
    fstab = tmp_path / "fstab"
    device_path = tmp_path / "dev" / "disk"
    device_path.parent.mkdir(parents=True, exist_ok=True)
    device_path.touch()

    def fake_candidates(self):  # type: ignore[override]
        return [device_path]

    monkeypatch.setattr(
        "forgeops_automation.operations.mount.BlockDeviceMountOperation._candidate_paths",
        fake_candidates,
    )

    responses = {
        ("blkid", "-o", "value", "-s", "TYPE", str(device_path)): [CommandResult(["blkid"], "", "", 2)],
        ("blkid", "-o", "value", "-s", "UUID", str(device_path)): [
            CommandResult(["blkid"], "aaaa-bbbb\n", "", 0)
        ],
        ("mountpoint", "-q", str(mount_dir)): [CommandResult(["mountpoint"], "", "", 1)],
    }
    executor = FakeExecutor(responses)
    op = BlockDeviceMountOperation(
        {
            "volume_id": "vol-123",
            "mount_point": str(mount_dir),
            "filesystem": "xfs",
            "fstab": str(fstab),
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert ("mount", str(mount_dir)) in executor.commands
    assert f"UUID=aaaa-bbbb {mount_dir} xfs defaults 0 2" in fstab.read_text()


def test_network_mount_handles_custom_source(tmp_path: Path):
    fstab = tmp_path / "fstab"
    mount_dir = tmp_path / "mnt" / "nfs"
    responses = {
        ("mountpoint", "-q", str(mount_dir)): [CommandResult(["mountpoint"], "", "", 1)],
    }
    executor = FakeExecutor(responses)
    op = NetworkMountOperation(
        {
            "source": "10.0.0.5:/exports/app",
            "mount_point": str(mount_dir),
            "fstype": "nfs4",
            "mount_options": ["_netdev", "rw"],
            "fstab": str(fstab),
        }
    )

    result = op.apply(HostConfig("local"), executor)

    assert result.changed is True
    assert f"10.0.0.5:/exports/app {mount_dir} nfs4 _netdev,rw 0 0" in fstab.read_text()
