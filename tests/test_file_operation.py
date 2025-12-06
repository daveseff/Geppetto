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


def test_file_symlink_creation(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("data")
    link = tmp_path / "link"
    spec = {"path": str(link), "link_target": str(target)}
    op = FileOperation(spec)

    result = op.apply(HostConfig("local"), build_executor())

    assert result.changed is True
    assert link.is_symlink()
    assert link.readlink() == target

    # Running again should be noop
    result = op.apply(HostConfig("local"), build_executor())
    assert result.changed is False


def test_file_symlink_removed(tmp_path: Path) -> None:
    target = tmp_path / "target2"
    target.write_text("data")
    link = tmp_path / "link2"
    os.symlink(target, link)
    spec = {"path": str(link), "link_target": str(target), "state": "absent"}
    op = FileOperation(spec)

    result = op.apply(HostConfig("local"), build_executor())

    assert result.changed is True
    assert not link.exists()


def test_file_template_renders_host_variables(tmp_path: Path, monkeypatch) -> None:
    template = tmp_path / "motd.tmpl"
    template.write_text("Hello ${name} from ${env}")
    target = tmp_path / "motd.txt"
    spec = {
        "path": str(target),
        "state": "present",
        "template": str(template),
        "variables": {"env": "Dev"},
    }
    host = HostConfig(name="local", variables={"name": "ForgeOps"})
    op = FileOperation(spec)

    result = op.apply(host, build_executor())

    assert result.changed is True
    assert target.read_text() == "Hello ForgeOps from Dev"
