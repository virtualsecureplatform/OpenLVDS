#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Localize the admitted LVT receiver frontend without changing its circuit."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import layout_receiver_variant as physical
import receiver_frontend_geometry as geometry
import probe_receiver_lvt_compact as native
from receiver_layout_reference import cached
from receiver_lvt_pair_experiment import source_variant
from dll_candidate_library import audited

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
TOP = 'openlvds_receiver_core'
PLACEMENT = 'Local frontend mirrors, tails, resistor loads and decision chain; only unused bias/monitor on folded M4 trunks'
PROFILE = dict(clamp_variant='unclamped_lvt_frontend_local',
    diagnostic_stage='complete_source_DC_and_clock_passed', placement=PLACEMENT)
sha = native.digest


def build(reference, matrix, clock):
    if not reference.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use the admitted compact LVT physical reference')
    report = json.loads((reference/'summary.json').read_text()); info = json.loads((reference/'extraction.json').read_text())
    native.validate_profile(report['identity'])
    source = source_variant((ROOT/'analog/openlvds.spice').read_text(), True)
    if not report['passed'] or cached(reference, report['identity'], source) != report:
        raise ValueError('LVT physical reference changed or failed')
    if any(sha(ROOT/'scripts'/n) != h for n, h in report['identity']['code'].items()):
        raise ValueError('Reference physical producer changed')
    if any(sha(ROOT/n) != h for n, h in report['identity']['source_proofs'].items()):
        raise ValueError('Reference source admission changed')
    audited(reference, info); gds = ROOT/report['designs'][TOP]['gds']
    if sha(gds) != info['gds_sha256'] or sha(reference/'candidate.spice') != info['source_sha256']:
        raise ValueError('Reference native model differs from source/GDS')
    proofs = native.source_gate(matrix, clock)
    metadata = dict(PROFILE, source_proofs=proofs, reference_layout=str(reference.relative_to(ROOT)),
        reference_summary_sha256=sha(reference/'summary.json'), reference_gds_sha256=sha(gds))
    producers = set(report['identity']['code']) | set(native.CODE) | {NAME, 'receiver_frontend_geometry.py'}
    names = producers | {'layout_receiver_variant.py', 'layout.py', 'lvs_utils.py', 'spice_library.py'}
    identity = dict(metadata, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)})
    out = ROOT/'build/diagnostics/receiver_layout'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = cached(out, identity, source)
        if result is not None:
            return out, result
        for name in names:
            path = out/'producer_snapshot'/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT/'scripts'/name).read_bytes())
        previous = physical.draw_macro
        try:
            physical.draw_macro = geometry.draw_macro
            actual, result = physical.build(source, metadata, producers)
        finally:
            physical.draw_macro = previous
        if actual != out or result['identity'] != identity:
            raise ValueError('Frontend-local physical identity changed')
        files = [out/(TOP+s) for s in ['.gds', '.sch.spice', '.lvs.log', '.drc.txt', '.drc_count.txt']]
        files += [out/'candidate.spice', out/'summary.json']
        (out/'physical_cache.json').write_text(json.dumps(dict(files={p.name: sha(p) for p in files}), indent=2)+'\n')
    return out, result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('reference', type=Path)
    p.add_argument('--dc-matrix', type=Path, required=True); p.add_argument('--source-clock', type=Path, required=True); a = p.parse_args()
    out, result = build(a.reference.resolve(), a.dc_matrix.resolve(), a.source_clock.resolve())
    print(json.dumps(dict(output=str(out), passed=result['passed'], qualified_phy=False)), flush=True)
    raise SystemExit(0 if result['passed'] else 1)
