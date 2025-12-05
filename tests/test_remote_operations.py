from pathlib import Path

from forgeops_automation.executors import CommandResult, Executor
from forgeops_automation.operations.remote import RemoteFileOperation, RpmInstallOperation
from forgeops_automation.types import HostConfig


class RecordingExecutor(Executor):
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


def test_remote_file_copies_local_source(tmp_path: Path):
    source = tmp_path / "payload.bin"
    dest = tmp_path / "output.bin"
    source.write_text("data")
    op = RemoteFileOperation({"source": str(source), "dest": str(dest), "mode": "0644"})
    result = op.apply(HostConfig("local"), RecordingExecutor())
    assert result.changed is True
    assert dest.read_text() == "data"


def test_remote_file_no_change_when_same(tmp_path: Path):
    source = tmp_path / "payload.txt"
    dest = tmp_path / "output.txt"
    source.write_text("content")
    dest.write_text("content")
    op = RemoteFileOperation({"source": str(source), "dest": str(dest)})
    result = op.apply(HostConfig("local"), RecordingExecutor())
    assert result.changed is False


def test_rpm_installs_when_missing(tmp_path: Path, monkeypatch):
    rpm_pkg = tmp_path / "pkg.rpm"
    rpm_pkg.write_text("rpmdata")

    class StubFetcher:
        def __init__(self, executor):
            pass

        def fetch(self, source: str) -> Path:  # noqa: ARG002
            return rpm_pkg

        @staticmethod
        def cleanup(path: Path) -> None:  # noqa: ARG002
            pass

    monkeypatch.setattr("forgeops_automation.operations.remote.RemoteFetcher", StubFetcher)

    responses = {
        ("rpm", "-q", "mypkg"): [CommandResult(["rpm"], "", "", 1)],
        ("rpm", "-Uvh", str(rpm_pkg)): [CommandResult(["rpm"], "", "", 0)],
    }
    executor = RecordingExecutor(responses)
    op = RpmInstallOperation({"name": "mypkg", "source": "s3://bucket/pkg.rpm"})
    result = op.apply(HostConfig("local"), executor)
    assert result.changed is True
    assert ("rpm", "-Uvh", str(rpm_pkg)) in executor.commands
