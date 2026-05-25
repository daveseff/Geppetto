from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_PLAN = Path("/etc/geppetto/plan.fops")
DEFAULT_LOG_FILE = Path("/var/log/geppetto/geppetto.log")


@dataclass
class GeppettoConfig:
    plan: Path = DEFAULT_PLAN
    state_file: Optional[Path] = None
    template_dir: Optional[Path] = None
    aws_region: Optional[str] = None
    aws_profile: Optional[str] = None
    config_repo_path: Optional[Path] = None
    config_repo_url: Optional[str] = None
    config_service_url: Optional[str] = None
    config_service_path: Optional[Path] = None
    config_service_host: Optional[str] = None
    config_service_ca_cert: Optional[Path] = None
    config_service_client_cert: Optional[Path] = None
    config_service_client_key: Optional[Path] = None
    log_file: Optional[Path] = DEFAULT_LOG_FILE
    plugin_modules: list[str] = field(default_factory=list)
    plugin_dirs: list[Path] = field(default_factory=list)


def load_config(path: Path) -> GeppettoConfig:
    if not path.exists():
        return GeppettoConfig()
    data = tomllib.loads(path.read_text())
    defaults = data.get("defaults", {})
    plan = Path(defaults.get("plan", DEFAULT_PLAN))
    state_file = defaults.get("state_file")
    template_dir = defaults.get("template_dir")
    aws_region = defaults.get("aws_region")
    aws_profile = defaults.get("aws_profile")
    config_repo_path = defaults.get("config_repo_path")
    config_repo_url = defaults.get("config_repo_url")
    config_service_url = defaults.get("config_service_url")
    config_service_path = defaults.get("config_service_path")
    config_service_host = defaults.get("config_service_host")
    config_service_ca_cert = defaults.get("config_service_ca_cert")
    config_service_client_cert = defaults.get("config_service_client_cert")
    config_service_client_key = defaults.get("config_service_client_key")
    log_file = defaults.get("log_file")
    plugin_modules = defaults.get("plugin_modules") or []
    plugin_dirs = defaults.get("plugin_dirs") or []

    if not isinstance(plugin_modules, list):
        raise ValueError("plugin_modules must be a list")
    if not isinstance(plugin_dirs, list):
        raise ValueError("plugin_dirs must be a list")

    return GeppettoConfig(
        plan=Path(plan),
        state_file=Path(state_file) if state_file else None,
        template_dir=Path(template_dir) if template_dir else None,
        aws_region=str(aws_region) if aws_region else None,
        aws_profile=str(aws_profile) if aws_profile else None,
        config_repo_path=Path(config_repo_path) if config_repo_path else None,
        config_repo_url=str(config_repo_url) if config_repo_url else None,
        config_service_url=str(config_service_url) if config_service_url else None,
        config_service_path=Path(config_service_path) if config_service_path else None,
        config_service_host=str(config_service_host) if config_service_host else None,
        config_service_ca_cert=Path(config_service_ca_cert) if config_service_ca_cert else None,
        config_service_client_cert=Path(config_service_client_cert) if config_service_client_cert else None,
        config_service_client_key=Path(config_service_client_key) if config_service_client_key else None,
        log_file=Path(log_file) if log_file else DEFAULT_LOG_FILE,
        plugin_modules=[str(m) for m in plugin_modules],
        plugin_dirs=[Path(p) for p in plugin_dirs],
    )
