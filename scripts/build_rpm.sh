#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
ForgeOps RPM builder
--------------------
Package a staged filesystem tree into an RPM suitable for RHEL 8 / Amazon Linux 2023.

Usage: build_rpm.sh --name NAME --version VERSION --payload DIR [options]

Required:
  -n, --name NAME             Package name
  -v, --version VERSION       Package version (e.g. 1.0.0)
  -p, --payload DIR           Directory containing files laid out relative to /

Optional:
  -r, --release RELEASE       Release number (default: 1)
  -s, --summary SUMMARY       RPM summary (default: "ForgeOps custom package")
  -d, --description TEXT      Long description (defaults to summary)
  -l, --license LICENSE       License string (default: MIT)
  -a, --arch ARCH             Target architecture (default: x86_64)
      --vendor VENDOR         Vendor string
      --url URL               Project URL
      --preinstall FILE       Scriptlet executed before install
      --postinstall FILE      Scriptlet executed after install
      --preuninstall FILE     Scriptlet executed before removal
      --postuninstall FILE    Scriptlet executed after removal
      --workdir DIR           rpmbuild topdir (default: ./build/rpmbuild)
      --output-dir DIR        Destination for RPM (default: ./dist)
      --dist-tag TAG          Optional distribution suffix appended to Release (e.g. .amzn2023)
  -h, --help                  Show this message

Example:
  scripts/build_rpm.sh -n forgeops-uf -v 0.1.0 -p payload --summary "UF config"
USAGE
}

fatal() {
  echo "[ERROR] $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fatal "Required command '$1' not found"
}

read_scriptlet() {
  local file="$1"
  [[ -z "$file" ]] && return
  [[ -f "$file" ]] || fatal "Scriptlet file not found: $file"
  cat "$file"
}

NAME=""
VERSION=""
RELEASE="1"
SUMMARY="ForgeOps custom package"
DESCRIPTION=""
LICENSE="MIT"
ARCH="x86_64"
PAYLOAD_DIR=""
VENDOR=""
URL=""
WORKDIR="$(pwd)/build/rpmbuild"
OUTPUT_DIR="$(pwd)/dist"
PREINSTALL=""
POSTINSTALL=""
PREUNINSTALL=""
POSTUNINSTALL=""
DIST_TAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--name) NAME="$2"; shift 2 ;;
    -v|--version) VERSION="$2"; shift 2 ;;
    -r|--release) RELEASE="$2"; shift 2 ;;
    -s|--summary) SUMMARY="$2"; shift 2 ;;
    -d|--description) DESCRIPTION="$2"; shift 2 ;;
    -l|--license) LICENSE="$2"; shift 2 ;;
    -a|--arch) ARCH="$2"; shift 2 ;;
    -p|--payload) PAYLOAD_DIR="$2"; shift 2 ;;
    --vendor) VENDOR="$2"; shift 2 ;;
    --url) URL="$2"; shift 2 ;;
    --preinstall) PREINSTALL="$2"; shift 2 ;;
    --postinstall) POSTINSTALL="$2"; shift 2 ;;
    --preuninstall) PREUNINSTALL="$2"; shift 2 ;;
    --postuninstall) POSTUNINSTALL="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --dist-tag) DIST_TAG="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    *) fatal "Unknown option: $1" ;;
  esac
done

[[ -n "$NAME" ]] || fatal "Missing --name"
[[ -n "$VERSION" ]] || fatal "Missing --version"
[[ -n "$PAYLOAD_DIR" ]] || fatal "Missing --payload"
PAYLOAD_DIR="$(realpath "$PAYLOAD_DIR")"
[[ -d "$PAYLOAD_DIR" ]] || fatal "Payload directory not found: $PAYLOAD_DIR"
[[ -n "$DESCRIPTION" ]] || DESCRIPTION="$SUMMARY"

require_cmd rpmbuild
require_cmd tar
require_cmd find

mkdir -p "$WORKDIR"/BUILD "$WORKDIR"/RPMS "$WORKDIR"/SOURCES "$WORKDIR"/SPECS "$WORKDIR"/SRPMS
mkdir -p "$OUTPUT_DIR"

stage_dir="$(mktemp -d)"
trap 'rm -rf "$stage_dir"' EXIT
src_root="$stage_dir/${NAME}-${VERSION}"
mkdir -p "$src_root"
cp -a "$PAYLOAD_DIR"/. "$src_root"/

tarball="$WORKDIR/SOURCES/${NAME}-${VERSION}.tar.gz"
tar -C "$stage_dir" -czf "$tarball" "${NAME}-${VERSION}"

filelist="$WORKDIR/SOURCES/${NAME}.files"
IGNORED_DIRS=("usr" "usr/bin" "usr/lib")
(
  cd "$PAYLOAD_DIR"
  find . -type d | sort | while read -r d; do
    [[ "$d" == "." ]] && continue
    rel="${d#./}"
    skip=false
    for ignored in "${IGNORED_DIRS[@]}"; do
      if [[ "$rel" == "$ignored" ]]; then
        skip=true
        break
      fi
    done
    $skip && continue
    printf '%%dir /%s\n' "$rel"
  done
  find . \( -type f -o -type l \) | sort | while read -r f; do
    printf '/%s\n' "${f#./}"
  done
) >"$filelist"

scriptlet_section() {
  local hook="$1"; local file="$2"
  [[ -z "$file" ]] && return
  printf '\n%%%s\n' "$hook"
  read_scriptlet "$file"
  printf '\n'
}

spec_file="$WORKDIR/SPECS/${NAME}.spec"
{
  printf '%%global debug_package %%{nil}\n'
  printf 'Name:           %s\n' "$NAME"
  printf 'Version:        %s\n' "$VERSION"
  printf 'Release:        %s%s\n' "$RELEASE" "$DIST_TAG"
  printf 'Summary:        %s\n' "$SUMMARY"
  printf 'License:        %s\n' "$LICENSE"
  [[ -n "$URL" ]] && printf 'URL:            %s\n' "$URL"
  [[ -n "$VENDOR" ]] && printf 'Vendor:         %s\n' "$VENDOR"
  printf 'BuildArch:      %s\n' "$ARCH"
  printf 'Source0:        %%{name}-%%{version}.tar.gz\n'
  printf 'AutoReqProv:    no\n\n'
  printf '%%description\n%s\n\n' "$DESCRIPTION"
  printf '%%prep\n%%setup -q\n\n'
  printf '%%build\n# no build step\n\n'
  printf '%%install\nrm -rf %%{buildroot}\nmkdir -p %%{buildroot}\ncp -a * %%{buildroot}\n\n'
  printf '%%files -f %%{_sourcedir}/%s.files\n\n' "$NAME"
  scriptlet_section pre "$PREINSTALL"
  scriptlet_section post "$POSTINSTALL"
  scriptlet_section preun "$PREUNINSTALL"
  scriptlet_section postun "$POSTUNINSTALL"
} >"$spec_file"

rpmbuild --define "_topdir $WORKDIR" --target "$ARCH" -bb "$spec_file"

latest_rpm=$(ls -1t "$WORKDIR/RPMS/$ARCH"/${NAME}-${VERSION}-${RELEASE}*.rpm | head -n1)
[[ -f "$latest_rpm" ]] || fatal "RPM build failed"

cp "$latest_rpm" "$OUTPUT_DIR"
echo "RPM created: $OUTPUT_DIR/$(basename "$latest_rpm")"
