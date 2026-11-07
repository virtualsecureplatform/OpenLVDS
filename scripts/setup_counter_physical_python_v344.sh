#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Isolated Python for native counter geometry and numerical evidence checks.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
counter_python="$root/build/tools/counter-physical-venv/bin/python"
if [[ -e "$counter_python" ]]; then
    "$counter_python" -c 'import numpy, scipy, klayout.db; assert (numpy.__version__, scipy.__version__, klayout.db.__version__) == ("2.1.3", "1.14.1", "0.30.7")'
    exit 0
fi
uv venv --python /usr/bin/python3 "$root/build/tools/counter-physical-venv"
uv pip install --python "$counter_python" --no-deps numpy==2.1.3 scipy==1.14.1 klayout==0.30.7
