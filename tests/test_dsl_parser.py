from pathlib import Path

import pytest

from forgeops_automation.dsl import DSLParseError, DSLParser


def test_parses_simple_plan(tmp_path: Path) -> None:
    sample = """
    node 'local' {
      connection => local
    }

    task 'bootstrap' on 'local' {
      package { ['git', 'python3']:
        ensure => present
      }

      file { '/tmp/forgeops-motd':
        ensure  => present
        mode    => '0644'
      }
    }
    """
    plan = DSLParser().parse_text(sample)
    assert set(plan.hosts) == {"local"}
    assert plan.tasks[0].actions[0].type == "package"
    assert plan.tasks[0].actions[0].data["packages"] == ["git", "python3"]
    assert plan.tasks[0].actions[1].data["mode"] == "0644"
    assert plan.tasks[0].actions[1].data["path"] == "/tmp/forgeops-motd"


def test_non_package_list_title_raises() -> None:
    parser = DSLParser()
    sample = """
    task 'demo' on 'local' {
      file { ['a', 'b']:
        ensure => present
      }
    }
    """
    with pytest.raises(DSLParseError):
        parser.parse_text(sample)


def test_parse_error_has_line_and_column() -> None:
    parser = DSLParser()
    bad = "task 't' on 'local' {\n  file {\n}\n"
    with pytest.raises(DSLParseError) as excinfo:
        parser.parse_text(bad)
    err = excinfo.value
    assert err.line == 3
    assert err.column is not None
