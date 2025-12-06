from pathlib import Path

from forgeops_automation.operations.sysctl import SysctlOperation
from forgeops_automation.types import HostConfig


class RecordingExecutor:
    def __init__(self):
        self.host = HostConfig(name="local")
        self.dry_run = False
        self.commands: list[list[str]] = []

    def run(self, command, *, check=True, mutable=True):  # noqa: ARG002
        self.commands.append(list(command))
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()

    def read_file(self, path: Path):
        try:
            return path.read_text()
        except FileNotFoundError:
            return None

    def write_file(self, path: Path, *, content: str, mode: int | None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if mode is not None:
            path.chmod(mode)
        return True, "content"

    def remove_path(self, path: Path):  # noqa: ARG002
        return False


def test_sysctl_applies_and_persists(tmp_path: Path) -> None:
    exec = RecordingExecutor()
    conf = tmp_path / "net.ipv4.conf"
    op = SysctlOperation(
        {
            "name": "net.ipv4.ip_forward",
            "value": 1,
            "conf_file": str(conf),
        }
    )

    result = op.apply(HostConfig("local"), exec)
    assert result.changed is True
    assert exec.commands[0] == ["sysctl", "-w", "net.ipv4.ip_forward=1"]
    assert conf.read_text() == "net.ipv4.ip_forward = 1\n"

    result = op.apply(HostConfig("local"), exec)
    assert result.changed is True  # runtime apply
    assert len(exec.commands) == 2
