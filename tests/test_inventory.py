from pathlib import Path
import textwrap

import pytest

from geppetto_automation.inventory import InventoryLoader


def test_loads_default_local_host(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.toml"
    plan_path.write_text(
        textwrap.dedent(
            """
            [[tasks]]
            name = "basic"

              [[tasks.actions]]
              type = "file"
              path = "/tmp/demo"
            """
        ).strip()
    )

    plan = InventoryLoader().load(plan_path)

    assert set(plan.hosts) == {"local"}
    assert plan.tasks[0].hosts == ["local"]
    assert plan.tasks[0].actions[0].type == "file"


def test_missing_action_type_raises(tmp_path: Path) -> None:
    plan_path = tmp_path / "bad.toml"
    plan_path.write_text(
        textwrap.dedent(
            """
            [[tasks]]
            name = "broken"

              [[tasks.actions]]
              path = "/tmp/demo"
            """
        ).strip()
    )

    loader = InventoryLoader()
    with pytest.raises(ValueError):
        loader.load(plan_path)


def test_loader_accepts_dsl(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.fops"
    plan_path.write_text(
        """
        task 'demo' on 'local' {
          package { 'git':
            ensure => present
          }
        }
        """.strip()
    )

    plan = InventoryLoader().load(plan_path)
    assert plan.tasks[0].actions[0].type == "package"
    assert plan.tasks[0].actions[0].data["name"] == "git"


def test_plan_dir_attached(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.toml"
    plan_path.write_text(
        """
        [hosts.local]
        connection = "local"

        [[tasks]]
        name = "demo"

          [[tasks.actions]]
          type = "file"
          path = "/tmp/demo"
          template = "templates/file.tmpl"
        """.strip()
    )

    plan = InventoryLoader().load(plan_path)
    action = plan.tasks[0].actions[0]
    assert action.data["_plan_dir"] == str(tmp_path)


def test_dsl_include(tmp_path: Path) -> None:
    sub = tmp_path / "sub.fops"
    sub.write_text(
        """
        task 'included' on 'local' {
          package { 'htop':
            ensure => present
          }
        }
        """.strip()
    )
    main = tmp_path / "main.fops"
    main.write_text(f"include '{sub.name}'\n")

    plan = InventoryLoader().load(main)
    assert plan.tasks[0].name == "included"
    assert plan.tasks[0].actions[0].data["name"] == "htop"


def test_toml_on_success(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.toml"
    plan_path.write_text(
        textwrap.dedent(
            """
            [[tasks]]
            name = "demo"
            hosts = ["local"]

              [[tasks.actions]]
              type = "exec"
              name = "set-policy"
              command = "true"

                [[tasks.actions.on_success]]
                type = "exec"
                name = "apply_authselect_profile"
                command = "authselect apply-changes"
            """
        ).strip()
    )

    plan = InventoryLoader().load(plan_path)
    action = plan.tasks[0].actions[0]
    assert len(action.on_success) == 1
    assert action.on_success[0].data["name"] == "apply_authselect_profile"
