from geppetto_automation import cli
from geppetto_automation.types import ActionResult


def test_format_result_failed(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    result = ActionResult(host="local", action="file", changed=False, details="boom", failed=True)
    line = cli.format_result(result)
    assert line.startswith("local::file failed - boom")


def test_format_result_success(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    result = ActionResult(host="local", action="package", changed=True, details="installed")
    line = cli.format_result(result)
    assert line.startswith("local::package changed - installed")
