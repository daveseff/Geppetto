#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

version="$(python3 - <<'PY'
from pathlib import Path
import re

text = Path("pyproject.toml").read_text()
match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
if not match:
    raise SystemExit("unable to determine version from pyproject.toml")
print(match.group(1))
PY
)"

rm -rf build
find dist -maxdepth 1 -type f -name 'geppetto_automation-*' -delete 2>/dev/null || true
find . -maxdepth 2 -type d \( -name '*.egg-info' -o -name '*.dist-info' \) -prune -exec rm -rf {} +

rpmbuild -bb --build-in-place geppetto-automation.spec

if [[ "${1:-}" == "--install" ]]; then
  rpm -Uvh --force "$HOME/rpmbuild/RPMS/noarch/geppetto_automation-${version}-1.noarch.rpm"
fi
