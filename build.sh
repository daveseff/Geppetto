#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

rpmbuild -bb --build-in-place geppetto-automation.spec

if [[ "${1:-}" == "--install" ]]; then
  rpm -Uvh --force ~/rpmbuild/RPMS/noarch/geppetto_automation-*.noarch.rpm
fi
