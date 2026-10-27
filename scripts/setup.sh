#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
destination="$root/build/apptainer/openlvds.sif"
mkdir -p "$(dirname "$destination")"
if [[ ${1:-} == --import && $# == 2 ]]; then
    cp --reflink=auto -- "$2" "$destination"
elif [[ $# == 0 ]]; then
    git -C "$root" submodule update --init thirdparties/OpenPLL
    make -C "$root/thirdparties/OpenPLL" apptainer-build
    cp --reflink=auto -- "$root/thirdparties/OpenPLL/build/apptainer/openpll-release-modern.sif" "$destination"
else
    echo 'Usage: scripts/setup.sh [--import existing-openpll-release-modern.sif]' >&2
    exit 2
fi
sha256sum "$destination" > "$destination.sha256"
printf 'Environment installed at %s\n' "$destination"
"$root/scripts/env.sh" --tools python3 scripts/tool_versions.py
