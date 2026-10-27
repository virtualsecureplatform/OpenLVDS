#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Record the actual environment, not the expected tool versions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
versions = {"pdk_root": os.environ["PDK_ROOT"]}
for tool, args in {
    "iverilog": ["iverilog", "-V"], "yosys": ["yosys", "-V"],
    "magic": ["magic", "--version"], "openroad": ["openroad", "-version"],
    "xyce": ["/opt/xyce/bin/Xyce", "-v"],
    "librelane": ["python3", "-m", "librelane", "--version"],
}.items():
    result = subprocess.run(args, capture_output=True, text=True)
    versions[tool] = {"returncode": result.returncode,
                      "version": (result.stdout + result.stderr).strip().splitlines()[0]}
versions["requirements_sha256"] = hashlib.sha256((root / "requirements.json").read_bytes()).hexdigest()
out = root / "build/tool_versions.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(versions, indent=2) + "\n")
print(json.dumps(versions, indent=2))
