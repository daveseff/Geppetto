from pathlib import Path

from geppetto_automation.executors import LocalExecutor
from geppetto_automation.operations.exec import ExecOperation
from geppetto_automation import secrets as secret_module
from geppetto_automation.types import HostConfig


def test_exec_runs_command(tmp_path: Path) -> None:
    host = HostConfig("local")
    target = tmp_path / "out.txt"
    op = ExecOperation({"name": "write-file", "command": f"echo hi > {target}"})
    result = op.apply(host, LocalExecutor(host))

    assert target.read_text().strip() == "hi"
    assert result.changed is True
    assert "ran" in result.details


def test_exec_skips_when_creates_exists(tmp_path: Path) -> None:
    host = HostConfig("local")
    target = tmp_path / "exists"
    target.write_text("present")
    op = ExecOperation({"name": "guard", "command": "echo should-not-run", "creates": str(target)})
    result = op.apply(host, LocalExecutor(host))

    assert result.changed is False
    assert "creates" in result.details


def test_exec_only_if_and_unless_guards() -> None:
    host = HostConfig("local")
    op_only_if = ExecOperation({"name": "guarded", "command": "echo skip", "only_if": "false"})
    result_only_if = op_only_if.apply(host, LocalExecutor(host))

    op_unless = ExecOperation({"name": "guarded2", "command": "echo skip", "unless": "true"})
    result_unless = op_unless.apply(host, LocalExecutor(host))

    assert result_only_if.changed is False
    assert "only_if" in result_only_if.details
    assert result_unless.changed is False
    assert "unless" in result_unless.details


def test_exec_respects_allowed_returns() -> None:
    host = HostConfig("local")
    op_ok = ExecOperation({"name": "rc-allowed", "command": "exit 3", "returns": [0, 3]})
    ok = op_ok.apply(host, LocalExecutor(host))

    op_fail = ExecOperation({"name": "rc-fail", "command": "exit 5"})
    fail = op_fail.apply(host, LocalExecutor(host))

    assert ok.changed is True
    assert ok.failed is False
    assert fail.failed is True
    assert "rc=5" in fail.details


def test_exec_passes_env() -> None:
    host = HostConfig("local")
    op = ExecOperation({"name": "env-check", "command": 'test "$FOO" = bar', "env": {"FOO": "bar"}})
    result = op.apply(host, LocalExecutor(host))

    assert result.failed is False
    assert result.changed is True


def test_exec_renders_secrets(monkeypatch, tmp_path: Path) -> None:
    host = HostConfig("local", variables={"password": {"aws_secret": "ad-join", "key": "pw"}})

    class FakeClient:
        def get_secret_value(self, SecretId):
            assert SecretId == "ad-join"
            return {"SecretString": '{"pw":"sekret"}'}

    class FakeBoto3:
        def client(self, name):
            assert name == "secretsmanager"
            return FakeClient()

    monkeypatch.setattr(secret_module, "boto3", FakeBoto3())

    target = tmp_path / "out.txt"
    op = ExecOperation(
        {
            "name": "write-secret",
            "command": f"/bin/echo ${{password}} > {target}",
        }
    )
    result = op.apply(host, LocalExecutor(host))

    assert result.failed is False
    assert target.read_text().strip() == "sekret"
