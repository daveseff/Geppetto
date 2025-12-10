from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_PLAN = Path("/etc/geppetto/plan.fops")


@dataclass
class GeppettoConfig:
    plan: Path = DEFAULT_PLAN
    state_file: Optional[Path] = None
    template_dir: Optional[Path] = None
    aws_region: Optional[str] = None
    aws_profile: Optional[str] = None


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
    return GeppettoConfig(
        plan=Path(plan),
        state_file=Path(state_file) if state_file else None,
        template_dir=Path(template_dir) if template_dir else None,
        aws_region=str(aws_region) if aws_region else None,
        aws_profile=str(aws_profile) if aws_profile else None,
    )
