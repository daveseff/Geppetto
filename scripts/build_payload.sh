#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
ForgeOps payload builder
------------------------
Creates a staging directory that mirrors /usr-based installation paths.

Usage: build_payload.sh [--python PATH] [--payload DIR]

Options:
  --python PATH    Python interpreter to use (default: python3)
  --payload DIR    Destination directory (default: build/payload)
  -h, --help       Show this help and exit

The script builds the ForgeOps wheel and installs it into the payload under
/usr/bin and /usr/lib so it can be consumed directly by build_rpm.sh.
USAGE
}

PYTHON_BIN="python3"
PAYLOAD_DIR="$(pwd)/build/payload"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --payload)
      PAYLOAD_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 1
}

# Ensure build module is available
if ! "$PYTHON_BIN" -m build --version >/dev/null 2>&1; then
  echo "Installing python-build module into the invoking environment"
  "$PYTHON_BIN" -m pip install --upgrade build >/dev/null
fi

"$PYTHON_BIN" -m build >/dev/null
wheel=$(ls -1t dist/forgeops_automation-*.whl 2>/dev/null | head -n1)
[[ -n "$wheel" ]] || { echo "Unable to locate built wheel in dist/" >&2; exit 1; }

rm -rf "$PAYLOAD_DIR"
mkdir -p "$PAYLOAD_DIR"

"$PYTHON_BIN" -m pip install "$wheel" --root "$PAYLOAD_DIR" --prefix /usr >/dev/null

echo "Payload created under $PAYLOAD_DIR"
