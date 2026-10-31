#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build an isolated Q-reset PFD and retain the preceding policy's rejection."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from pfd_qreset_policy import pfd_qreset_paths_retained

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def run(out, tag):
    out = out.resolve()
    if not out.is_relative_to(ROOT / 'build/diagnostics'):
        raise ValueError('Use an isolated diagnostic directory')
    if (out / 'summary.json').exists():
        raise ValueError('Preserve existing physical results; choose a new artifact directory')
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'sky130/experiments/lvds_pfd_area_qreset.v'
    if not pfd_qreset_paths_retained(source.read_text()):
        raise ValueError('Q-reset candidate source violates its structural policy')
    producers = [Path(__file__), ROOT / 'scripts/pfd_qreset_policy.py',
                 ROOT / 'scripts/harden.py', ROOT / 'scripts/physical_policy.py']
    code = {p.name: digest(p) for p in producers}
    archive = out / 'producer_archive'; archive.mkdir(exist_ok=True)
    for p in producers:
        (archive / p.name).write_bytes(p.read_bytes())
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/harden.py'),
        '--design', 'pfd', '--pfd-source', str(source), '--pfd-policy', 'pulse-area',
        '--artifact-dir', str(out), '--tag', tag], cwd=ROOT, capture_output=True, text=True)
    (out / 'harden_console.log').write_text(result.stdout + result.stderr)
    summary = out / 'summary.json'
    if not summary.exists():
        result.check_returncode()
        raise ValueError('Physical flow produced no result')
    # The unchanged hardener rejects internal-Q coincidence under its buffered
    # reset policy. Preserve that result, then independently apply the new policy.
    preceding = out / 'preceding_policy_check.json'
    preceding.write_bytes(summary.read_bytes())
    record = json.loads(summary.read_text())
    netlist = ROOT / record['run'] / 'final/nl/lvds_pfd.nl.v'
    structural = netlist.exists() and pfd_qreset_paths_retained(netlist.read_text())
    unchanged = code == {p.name: digest(p) for p in producers}
    passed = (result.returncode in [0, 1] and record['returncode'] == 0 and record['inputs_unchanged'] and
              record['delay_cells_absent'] and structural and unchanged)
    record.update(passed=bool(passed), interface_verified=bool(structural),
                  pfd_policy='pulse-area-q-reset', qualified_phy=False,
                  qreset_producer_code=code, qreset_producers_unchanged=unchanged,
                  preceding_policy_check_sha256=digest(preceding))
    atomic(summary, record)
    print(json.dumps(dict(passed=passed, policy=record['pfd_policy'],
                          summary=str(summary.relative_to(ROOT)), qualified_phy=False)), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-dir', required=True, type=Path)
    parser.add_argument('--tag', default='qreset')
    args = parser.parse_args()
    sys.exit(run(args.artifact_dir, args.tag))
