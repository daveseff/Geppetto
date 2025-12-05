from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib


DEFAULT_PLAN = Path("/etc/forgeops/plan.fops")


@dataclass
class ForgeOpsConfig:
    plan: Path = DEFAULT_PLAN
    state_file: Path | None = None
    template_dir: Path | None = None


def load_config(path: Path) -> ForgeOpsConfig:
    if not path.exists():
        return ForgeOpsConfig()
    data = tomllib.loads(path.read_text())
    defaults = data.get("defaults", {})
    plan = Path(defaults.get("plan", DEFAULT_PLAN))
    state_file = defaults.get("state_file")
    template_dir = defaults.get("template_dir")
    return ForgeOpsConfig(
        plan=Path(plan),
        state_file=Path(state_file) if state_file else None,
        template_dir=Path(template_dir) if template_dir else None,
    )
