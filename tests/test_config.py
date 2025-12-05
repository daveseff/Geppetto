from pathlib import Path

from forgeops_automation.config import ForgeOpsConfig, load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.conf")
    assert isinstance(config, ForgeOpsConfig)
    assert config.plan == Path("/etc/forgeops/plan.fops")


def test_load_config_overrides(tmp_path: Path) -> None:
    cfg_path = tmp_path / "main.conf"
    cfg_path.write_text(
        """
        [defaults]
        plan = "/opt/forgeops/plan.fops"
        state_file = "/var/lib/forgeops/state.json"
        template_dir = "/opt/forgeops/templates"
        """
    )

    config = load_config(cfg_path)
    assert config.plan == Path("/opt/forgeops/plan.fops")
    assert config.state_file == Path("/var/lib/forgeops/state.json")
    assert config.template_dir == Path("/opt/forgeops/templates")
