#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
image=${OPENLVDS_IMAGE:-$root/build/apptainer/openlvds.sif}
[[ -f "$image" ]] || { echo 'Run scripts/setup.sh first.' >&2; exit 1; }
[[ $# -gt 0 ]] || { echo 'Usage: scripts/env.sh [--tools] command [args...]' >&2; exit 2; }
tools=0
spice=${OPENLVDS_SPICE:-xyce}
while [[ $# -gt 0 ]]; do
    case $1 in
        --tools) tools=1; shift;;
        --ngspice) spice=ngspice; shift;;
        --xyce) spice=xyce; shift;;
        *) break;;
    esac
done
[[ $# -gt 0 ]] || { echo 'A command is required.' >&2; exit 2; }
mkdir -p "$root/build/cache/apptainer"
export APPTAINER_CACHEDIR="$root/build/cache/apptainer"
args=(exec --userns --writable-tmpfs --cleanenv --containall
    --bind "$root:/work/OpenLVDS" --pwd /work/OpenLVDS
    --env NIX_REMOTE=local --env NIX_BUILD_SHELL=/bin/bash
    --env PDK_ROOT=/opt/pdk/ciel/sky130/versions/1689ac3f2dc763876eaf967227c7dfe831b031ae
    --env PDK=sky130A --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1
    --env OPENLVDS_SPICE="$spice"
    --env OPENLVDS_SPICE_SLOTS="${OPENLVDS_SPICE_SLOTS:-6}"
    "$image")
if (( tools )); then
    printf -v command '%q ' "$@"
    exec apptainer "${args[@]}" nix-shell /opt/librelane/shell.nix --run "$command"
fi
exec apptainer "${args[@]}" "$@"
