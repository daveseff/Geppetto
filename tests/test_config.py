from pathlib import Path

from geppetto_automation.config import GeppettoConfig, load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.conf")
    assert isinstance(config, GeppettoConfig)
    assert config.plan == Path("/etc/geppetto/plan.fops")


def test_load_config_overrides(tmp_path: Path) -> None:
    cfg_path = tmp_path / "main.conf"
    cfg_path.write_text(
        """
        [defaults]
        plan = "/opt/geppetto/plan.fops"
        state_file = "/var/lib/geppetto/state.json"
        template_dir = "/opt/geppetto/templates"
        aws_region = "ap-southeast-2"
        aws_profile = "myprofile"
        config_repo_path = "/opt/geppetto/config"
        config_repo_url = "https://example.invalid/geppetto-config.git"
        """
    )

    config = load_config(cfg_path)
    assert config.plan == Path("/opt/geppetto/plan.fops")
    assert config.state_file == Path("/var/lib/geppetto/state.json")
    assert config.template_dir == Path("/opt/geppetto/templates")
    assert config.aws_region == "ap-southeast-2"
    assert config.aws_profile == "myprofile"
    assert config.config_repo_path == Path("/opt/geppetto/config")
    assert config.config_repo_url == "https://example.invalid/geppetto-config.git"
