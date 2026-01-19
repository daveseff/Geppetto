from pathlib import Path

from geppetto_automation.executors import CommandResult, LocalExecutor
from geppetto_automation.operations.ca_cert import CaCertOperation
from geppetto_automation.types import HostConfig


class FakeExecutor(LocalExecutor):
    def __init__(self, host: HostConfig, cert_text: str):
        super().__init__(host)
        self.commands: list[list[str]] = []
        self.alias_present = False
        self.cert_text = cert_text

    def run(  # type: ignore[override]
        self,
        command,
        *,
        check: bool = True,
        mutable: bool = True,  # noqa: ARG002
        env=None,  # noqa: ARG002
        cwd=None,  # noqa: ARG002
        timeout=None,  # noqa: ARG002
    ):
        cmd = list(command)
        self.commands.append(cmd)
        if cmd[0] == "keytool":
            return self._handle_keytool(cmd)
        return CommandResult(cmd, "", "", 0)

    def _handle_keytool(self, cmd: list[str]) -> CommandResult:
        if "-list" in cmd:
            return CommandResult(cmd, "", "", 0 if self.alias_present else 1)
        if "-exportcert" in cmd:
            return CommandResult(cmd, self.cert_text, "", 0 if self.alias_present else 1)
        if "-importcert" in cmd:
            self.alias_present = True
            return CommandResult(cmd, "", "", 0)
        if "-delete" in cmd:
            self.alias_present = False
            return CommandResult(cmd, "", "", 0)
        return CommandResult(cmd, "", "", 0)


def test_ca_cert_installs_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    cert_text = (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIBtTCCAVugAwIBAgIJAODxMZJb9d7HMAoGCCqGSM49BAMCMBUxEzARBgNVBAMM\n"
        "CkdlcHBldHRvMB4XDTI0MDUwMTAwMDAwMFoXDTM0MDQyODAwMDAwMFowFTETMBEG\n"
        "A1UEAwwKR2VwcGV0dG8wWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAQ6LujZy4cv\n"
        "F0u6bM1v9qI1kP6JUL7oM6L8Xloq5ig42tRx9ryvFQm5wGQ5n1RP0Ww9dQ9F7bQy\n"
        "ie8Vt/cHo1MwUTAdBgNVHQ4EFgQUv3bM1C2r8c2VQ7sV7wC1A0GFMx4wHwYDVR0j\n"
        "BBgwFoAUv3bM1C2r8c2VQ7sV7wC1A0GFMx4wDwYDVR0TAQH/BAUwAwEB/zAKBggq\n"
        "hkjOPQQDAgNJADBGAiEA4D0Q4zW4qXk+GZr3wYsoN8Esiv7w2v3E6fCxQ7gCIQDm\n"
        "cH/2ZB4Sg0YJg5W7tH7E6mB8QzT9q2YQH8a7hA==\n"
        "-----END CERTIFICATE-----\n"
    )
    source = tmp_path / "corp.pem"
    source.write_text(cert_text)
    trust_dir = tmp_path / "anchors"
    keystore = tmp_path / "cacerts"
    keystore.write_text("dummy")

    host = HostConfig("local")
    executor = FakeExecutor(host, cert_text)
    monkeypatch.setattr(CaCertOperation, "_detect_os_family", lambda self: "rhel")

    op = CaCertOperation(
        {
            "name": "corp",
            "path": str(source),
            "os_trust_dir": str(trust_dir),
            "java_keystore": str(keystore),
        }
    )
    result = op.apply(host, executor)

    assert result.changed is True
    assert (trust_dir / "corp.pem").exists()
    assert any(cmd[0] == "update-ca-trust" for cmd in executor.commands)
    assert any(cmd[0] == "keytool" and "-importcert" in cmd for cmd in executor.commands)

    executor.commands.clear()
    result = op.apply(host, executor)
    assert result.changed is False
    assert not any(cmd[0] == "update-ca-trust" for cmd in executor.commands)


def test_ca_cert_removes_from_os_and_java(tmp_path: Path, monkeypatch) -> None:
    cert_text = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
    source = tmp_path / "corp.pem"
    source.write_text(cert_text)
    trust_dir = tmp_path / "anchors"
    trust_dir.mkdir()
    target = trust_dir / "corp.pem"
    target.write_text(cert_text)
    keystore = tmp_path / "cacerts"
    keystore.write_text("dummy")

    host = HostConfig("local")
    executor = FakeExecutor(host, cert_text)
    executor.alias_present = True
    monkeypatch.setattr(CaCertOperation, "_detect_os_family", lambda self: "rhel")

    op = CaCertOperation(
        {
            "name": "corp",
            "path": str(source),
            "os_trust_dir": str(trust_dir),
            "java_keystore": str(keystore),
            "state": "absent",
        }
    )
    result = op.apply(host, executor)

    assert result.changed is True
    assert not target.exists()
    assert any(cmd[0] == "update-ca-trust" for cmd in executor.commands)
    assert any(cmd[0] == "keytool" and "-delete" in cmd for cmd in executor.commands)
