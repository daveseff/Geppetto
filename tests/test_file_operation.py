from pathlib import Path
import os

from geppetto_automation.executors import LocalExecutor
from geppetto_automation.operations.file import FileOperation
from geppetto_automation import secrets as secret_module
from geppetto_automation.types import HostConfig


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


def test_file_directory_creates_and_sets_mode(tmp_path: Path) -> None:
    target = tmp_path / "config.d"
    spec = {"path": str(target), "state": "directory", "mode": "0750"}
    op = FileOperation(spec)

    result = op.apply(HostConfig("local"), build_executor())

    assert result.changed is True
    assert target.is_dir()
    assert oct(os.stat(target).st_mode & 0o777) == "0o750"

    # Second run should be idempotent
    result = op.apply(HostConfig("local"), build_executor())
    assert result.changed is False


def test_file_directory_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "config-dir"
    target.write_text("old")
    spec = {"path": str(target), "state": "directory"}
    op = FileOperation(spec)

    result = op.apply(HostConfig("local"), build_executor())

    assert result.changed is True
    assert target.is_dir()


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
    host = HostConfig(name="local", variables={"name": "Geppetto"})
    op = FileOperation(spec)

    result = op.apply(host, build_executor())

    assert result.changed is True
    assert target.read_text() == "Hello Geppetto from Dev"


def test_file_template_renders_jinja_loop(tmp_path: Path) -> None:
    template = tmp_path / "hosts.j2"
    template.write_text(
        "allowed_hosts:\n"
        "{% for host in allowed_hosts %}"
        "  - {{ host }}\n"
        "{% endfor %}"
    )
    target = tmp_path / "hosts.yaml"
    spec = {
        "path": str(target),
        "state": "present",
        "template": str(template),
        "variables": {"allowed_hosts": ["a.example", "b.example"]},
    }
    host = HostConfig(name="local")
    op = FileOperation(spec)

    result = op.apply(host, build_executor())

    assert result.changed is True
    assert "a.example" in target.read_text()


def test_file_template_missing_jinja_var_is_empty(tmp_path: Path) -> None:
    template = tmp_path / "optional.j2"
    template.write_text(
        "primary = {{ primary_group }}\n"
        "{% if additional_admin_groups %}"
        "admins = {{ additional_admin_groups|join(',') }}\n"
        "{% endif %}"
    )
    target = tmp_path / "out.txt"
    spec = {
        "path": str(target),
        "state": "present",
        "template": str(template),
        "variables": {"primary_group": "wheel"},
    }
    host = HostConfig(name="local")
    op = FileOperation(spec)

    result = op.apply(host, build_executor())

    assert result.changed is True
    assert "primary = wheel" in target.read_text()


def test_file_template_renders_secret(monkeypatch, tmp_path: Path) -> None:
    template = tmp_path / "secret.tmpl"
    template.write_text("password={{ password }}\n")
    target = tmp_path / "out.txt"

    class FakeClient:
        def __init__(self):
            self.calls = []

        def get_secret_value(self, SecretId):
            self.calls.append(SecretId)
            return {"SecretString": '{"password":"s3cr3t"}'}

    fake_client = FakeClient()

    class FakeBoto3:
        def client(self, name):
            assert name == "secretsmanager"
            return fake_client

    monkeypatch.setattr(secret_module, "boto3", FakeBoto3())

    spec = {
        "path": str(target),
        "state": "present",
        "template": str(template),
        "variables": {"password": {"aws_secret": "app/creds", "key": "password"}},
    }
    host = HostConfig(name="local")
    op = FileOperation(spec)

    result = op.apply(host, build_executor())

    assert result.changed is True
    assert "s3cr3t" in target.read_text()
