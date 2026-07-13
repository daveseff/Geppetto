from __future__ import annotations

import pytest

from geppetto_automation.cli import Ansi, _format_certificate_status_line, main, parse_args, parse_cert_args


def test_main_help_lists_certificate_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--help"])

    output = capsys.readouterr().out
    assert "Certificate commands:" in output
    assert "geppetto-auto cert init" in output
    assert "geppetto-auto cert status" in output
    assert "geppetto-auto cert clean" in output


def test_cert_help_uses_nested_command_prog(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_cert_args(["init", "--help"])

    output = capsys.readouterr().out
    assert "usage: geppetto-auto cert init" in output


def test_help_command_prints_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["help"]) == 0

    output = capsys.readouterr().out
    assert "Geppetto automation runner" in output
    assert "geppetto-auto cert init" in output


def test_help_command_prints_nested_cert_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["help", "cert", "clean"]) == 0

    output = capsys.readouterr().out
    assert "usage: geppetto-auto cert clean" in output
    assert "Remove local client key, CSR, CA, and certificate" in output


def test_cert_help_command_prints_cert_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cert", "help"]) == 0

    output = capsys.readouterr().out
    assert "usage: geppetto-auto cert" in output
    assert "init" in output


def test_cert_help_command_prints_nested_cert_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cert", "help", "clean"]) == 0

    output = capsys.readouterr().out
    assert "usage: geppetto-auto cert clean" in output
    assert "Remove local client key, CSR, CA, and certificate" in output


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["cert", "init", "help"], "usage: geppetto-auto cert init"),
        (["cert", "status", "help"], "usage: geppetto-auto cert status"),
        (["cert", "clean", "help"], "usage: geppetto-auto cert clean"),
        (["help", "cert", "init"], "usage: geppetto-auto cert init"),
        (["help", "cert", "status"], "usage: geppetto-auto cert status"),
        (["help", "cert", "clean"], "usage: geppetto-auto cert clean"),
    ],
)
def test_all_agent_subcommands_support_help_forms(
    argv: list[str],
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(argv) == 0

    output = capsys.readouterr().out
    assert expected in output


@pytest.mark.parametrize(
    ("value", "color"),
    [
        ("present:/etc/geppetto/pki/host1.crt", Ansi.GREEN),
        ("missing:/etc/geppetto/pki/host1.crt", Ansi.RED),
        ("expired:/etc/geppetto/pki/host1.crt", Ansi.YELLOW),
    ],
)
def test_certificate_status_line_colorizes_known_states(
    value: str,
    color: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("geppetto_automation.cli.sys.stdout.isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert _format_certificate_status_line("client_cert", value) == (
        f"client_cert: {color}{value}{Ansi.RESET}"
    )


def test_certificate_status_line_respects_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("geppetto_automation.cli.sys.stdout.isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")

    assert _format_certificate_status_line("client_cert", "missing:/tmp/client.crt") == (
        "client_cert: missing:/tmp/client.crt"
    )
