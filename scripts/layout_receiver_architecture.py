#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build an isolated compact receiver after architecture DC pilots and rate pass."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import layout_receiver_variant as physical
import receiver_compact_geometry as compact
import receiver_architecture_observations as observed
import receiver_architecture_rate as rate
from receiver_layout_reference import cached

ROOT = Path(__file__).resolve().parents[1]
TOP = 'openlvds_receiver_core'
NAME = Path(__file__).name
sha = observed.experiment.digest


def source_gate(matrix, rate_root):
    if not matrix.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_matrix'):
        raise ValueError('Use the bounded architecture DC matrix')
    manifest = json.loads((matrix/'manifest.json').read_text()); identity = manifest['identity']
    pilots = identity['children'][:3]
    if len(pilots) != 3 or {(c['process'], c['temperature']) for c in pilots} != {('tt', 25), ('sf', 40), ('fs', 40)}:
        raise ValueError('Require exactly the original three DC pilots')
    if any(not (ROOT/c['root']/'summary.json').is_file() for c in pilots):
        raise ValueError('Complete all three architecture DC pilots first')
    if not (rate_root/'summary.json').is_file():
        raise ValueError('Complete the nominal architecture rate test first')
    if any(sha(ROOT/n) != h for n, h in identity['inputs'].items()) or any(
            sha(ROOT/'scripts'/n) != h for n, h in identity['code'].items()):
        raise ValueError('Architecture matrix context changed')
    paths = [matrix/'manifest.json']
    for child in pilots:
        folder = ROOT/child['root']; m = json.loads((folder/'manifest.json').read_text())
        if sha(folder/'manifest.json') != child['manifest_sha256'] or m['identity']['architecture_variant'] != identity['variant']:
            raise ValueError('Architecture DC pilot binding changed')
        report = observed.run(folder)
        if not (report['architecture']['metrics']['passed'] and report['architecture']['observations']['observed_thin_guard_passed']):
            raise ValueError('Architecture DC pilot failed')
        paths.extend(folder/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn'])
    result = rate.run(rate_root)
    if result['variant'] != identity['variant'] or not result['metrics']['passed']:
        raise ValueError('Matched architecture rate test failed or differs from DC pilots')
    paths.extend(rate_root/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn'])
    return identity['variant'], {str(p.relative_to(ROOT)): sha(p) for p in paths}


def build(matrix, rate_root):
    variant, proofs = source_gate(matrix, rate_root)
    source = observed.experiment.source_variant((ROOT/'analog/openlvds.spice').read_text(), True, variant)
    metadata = dict(architecture_variant=variant, clamp_variant='unclamped_architecture_compact',
        placement='Four folded frontend columns on shared M4 trunks; packed summing/decision/restoration row; critical M3 buses first',
        diagnostic_stage='three_passing_source_DC_pilots_and_nominal_rate', source_proofs=proofs)
    matrix_manifest = json.loads((matrix/'manifest.json').read_text())
    producers = set(matrix_manifest['identity']['code']) | {NAME, 'receiver_architecture_rate.py',
        'receiver_compact_geometry.py', 'receiver_layout_reference.py'}
    names = producers | {'layout_receiver_variant.py', 'layout.py', 'lvs_utils.py', 'spice_library.py'}
    identity = dict(metadata, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)})
    out = ROOT/'build/diagnostics/receiver_layout'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = cached(out, identity, source)
        if report is not None:
            return out, report
        previous = physical.draw_macro
        try:
            physical.draw_macro = compact.draw_macro
            actual, report = physical.build(source, metadata, producers)
        finally:
            physical.draw_macro = previous
        if actual != out or report['identity'] != identity:
            raise ValueError('Architecture compact physical identity changed')
        files = [out/(TOP+s) for s in ['.gds', '.sch.spice', '.lvs.log', '.drc.txt', '.drc_count.txt']]
        files += [out/'candidate.spice', out/'summary.json']
        (out/'physical_cache.json').write_text(json.dumps(dict(files={p.name: sha(p) for p in files}), indent=2)+'\n')
    return out, report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('matrix', type=Path)
    p.add_argument('--rate', type=Path, required=True); a = p.parse_args()
    out, report = build(a.matrix.resolve(), a.rate.resolve())
    print(json.dumps(dict(output=str(out), passed=report['passed'], qualified_phy=False)), flush=True)
    raise SystemExit(0 if report['passed'] else 1)
