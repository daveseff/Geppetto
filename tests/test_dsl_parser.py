from pathlib import Path

import pytest

from geppetto_automation.dsl import DSLParseError, DSLParser


def test_parses_simple_plan(tmp_path: Path) -> None:
    sample = """
    node 'local' {
      connection => local
    }

    task 'bootstrap' on 'local' {
      package { ['git', 'python3']:
        ensure => present
      }

      file { '/tmp/geppetto-motd':
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
    assert plan.tasks[0].actions[1].data["path"] == "/tmp/geppetto-motd"


def test_non_package_list_title_raises() -> None:
    parser = DSLParser()
    sample = """
    task 'demo' on 'local' {
      file { ['a', 'b']:
        ensure => present
      }
    }
    """
    plan = parser.parse_text(sample)
    assert len(plan.tasks[0].actions) == 2
    assert plan.tasks[0].actions[0].data["path"] == "a"
    assert plan.tasks[0].actions[1].data["path"] == "b"


def test_other_list_title_raises() -> None:
    parser = DSLParser()
    sample = """
    task 'demo' on 'local' {
      service { ['a', 'b']:
        state => running
      }
    }
    """
    with pytest.raises(DSLParseError):
        parser.parse_text(sample)


def test_map_literal_in_dsl() -> None:
    parser = DSLParser()
    sample = """
    node 'local' {
      secret => { aws_secret => 'name', key => 'password' }
    }
    """
    plan = parser.parse_text(sample)
    assert plan.hosts["local"].variables["secret"]["aws_secret"] == "name"


def test_number_literal_in_dsl() -> None:
    parser = DSLParser()
    sample = """
    task 'demo' on 'local' {
      exec { 'timeout-test':
        timeout => 10
      }
    }
    """
    plan = parser.parse_text(sample)
    assert plan.tasks[0].actions[0].data["timeout"] == 10


def test_parse_error_has_line_and_column() -> None:
    parser = DSLParser()
    bad = "task 't' on 'local' {\n  file {\n}\n"
    with pytest.raises(DSLParseError) as excinfo:
        parser.parse_text(bad)
    err = excinfo.value
    assert err.line == 3
    assert err.column is not None


def test_on_success_and_failure_blocks_parse() -> None:
    sample = """
    task 'demo' on 'local' {
      exec { 'set-crypto-policy':
        command => '/usr/bin/update-crypto-policies --set DEFAULT:AD-SUPPORT'
        on_success => {
          exec { 'apply_authselect_profile':
            command => 'authselect apply-changes'
          }
        }
        on_failure => {
          exec { 'rollback_policy':
            command => '/usr/bin/update-crypto-policies --set DEFAULT'
          }
        }
      }
    }
    """
    plan = DSLParser().parse_text(sample)
    action = plan.tasks[0].actions[0]
    assert len(action.on_success) == 1
    assert action.on_success[0].data["name"] == "apply_authselect_profile"
    assert len(action.on_failure) == 1
    assert action.on_failure[0].data["name"] == "rollback_policy"
