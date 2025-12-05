from pathlib import Path
import os

from forgeops_automation.executors import LocalExecutor
from forgeops_automation.operations.file import FileOperation
from forgeops_automation.types import HostConfig


def build_executor() -> LocalExecutor:
    host = HostConfig(name="local")
    return LocalExecutor(host, dry_run=False)


def test_file_present_creates_content(tmp_path: Path) -> None:
    target = tmp_path / "config.txt"
    spec = {
        "path": str(target),
        "state": "present",
        "content": "hello",
        "mode": "0640",
    }
    op = FileOperation(spec)
    result = op.apply(HostConfig("local"), build_executor())

    assert result.changed is True
    assert target.read_text() == "hello"
    assert oct(os.stat(target).st_mode & 0o777) == "0o640"


def test_file_absent_removes_files(tmp_path: Path) -> None:
    target = tmp_path / "obsolete.txt"
    target.write_text("old")
    spec = {"path": str(target), "state": "absent"}
    op = FileOperation(spec)
    result = op.apply(HostConfig("local"), build_executor())

    assert result.changed is True
    assert not target.exists()
