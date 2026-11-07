#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Apply current native/Schur proofs to unchanged retained MIM fine-cell RC."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import extract_mim_switch_unit_v2 as small
import extract_mim_switch_2x3_v2 as large
import build_parallel_output_cell_v111 as proof
import native_bank_inventory_v51 as inventory
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit

ROOT = small.ROOT
VERSION = 'retained-mim-fine-cells-unchanged-rc-native-schur-requalification-v320.1'
CONTEXT = 'retained_mim_fine_rc_v320'
PROFILES = (
    ('2x2', small, 'mim_switch_unit_rc_v2/b1438bbf3193eb2f',
     'mim_switch_unit_verification_v2/e0f493e7d69328f9'),
    ('2x3', large, 'mim_switch_2x3_rc_v2/942b90d393388692',
     'mim_switch_2x3_verification_v2/26f440d15e6e9da1'),
)
PORTS = ['NODE', 'EN', 'ENB', 'VDD', 'VSS']
SCOPE = ('Current exact-reduction, elementwise-passivity, native-parameter/topology and '
         'independent Schur terminal-current proofs of unchanged retained 2x2/2x3 MIM '
         'fine-cell GDS-derived RC; no new extraction, geometry, bank substitution, '
         'periodic timing, shared-wire RC, PVT or PHY admission')


def atomic(path, value):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def retained(profile):
    label, module, artifact, receipt = profile
    parent = ROOT/'build/diagnostics'/artifact
    manifest, physical = module.bound(parent)
    if parent.name != hashlib.sha256(json.dumps(manifest['identity'], sort_keys=True).encode()).hexdigest()[:16]:
        raise ValueError('Retained extraction identity changed')
    receipt_path = ROOT/'build/diagnostics'/receipt/'summary.json'
    report = json.loads(receipt_path.read_text())
    ri = report['identity']
    bindings = {**ri['witnesses'], **ri['code']}
    if (ri['artifact'] != str(parent.relative_to(ROOT))
            or receipt_path.parent.name != hashlib.sha256(json.dumps(ri, sort_keys=True).encode()).hexdigest()[:16]
            or report['rc_topology_passed'] is not True
            or any(sha(ROOT/n) != h for n, h in bindings.items())):
        raise ValueError('Retained independent extraction receipt changed')
    info = report['verified_model']
    text = module.checked_netlist(info)
    geometry = ROOT/manifest['identity']['parent']
    name = module.NAME
    reference = geometry/(name+'.lvs.spice')
    if (physical['drc_count'] != '0' or physical['lvs_passed'] is not True
            or info['ports'] != PORTS or info['ports_verified'] is not True
            or info['gds_sha256'] != sha(geometry/(name+'.gds'))
            or info['source_scope_sha256'] != sha(geometry/(name+'.sch.spice'))
            or sha(ROOT/info['raw_netlist']) != info['reduction']['source_sha256']
            or sha(ROOT/info['netlist']) != info['netlist_sha256']
            or not all(audit(t)['elementwise_passive_passed']
                       for t in (text, (ROOT/info['raw_netlist']).read_text()))):
        raise ValueError('Retained geometry, RC interface, bytes or passivity changed')
    ports, devices = inventory.native_leaves(collapse(text), name)
    expected = {'sky130_fd_pr__nfet_01v8': 2, 'sky130_fd_pr__pfet_01v8': 1,
                'sky130_fd_pr__cap_mim_m3_1': 2}
    if ports != PORTS or dict(Counter(d['model'] for d in devices)) != expected:
        raise ValueError('Retained MIM fine-cell native inventory changed')
    paths = [receipt_path, reference, *[parent/n for n in ('manifest.json', 'summary.json', 'state.json')],
             *[ROOT/n for n in bindings], *[ROOT/n for n in manifest['identity']['code']],
             *[ROOT/n for n in manifest['identity']['parent_files']]]
    pm = json.loads((geometry/'manifest.json').read_text())['identity']
    external = {**pm['pdk_files']}
    setup = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    external[str(setup)] = sha(setup)
    return dict(variant=label, macro=name, extraction=info,
                reference=str(reference.relative_to(ROOT)), original_native_mos=3,
                original_native_mims=2, original_drc_count='0', original_lvs_passed=True), paths, external


def prepare():
    rows, paths, external = [], [], {}
    for profile in PROFILES:
        row, files, pdk = retained(profile)
        rows.append(row)
        paths += files
        external.update(pdk)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    paths += [ROOT/'scripts/exact_rc_candidate.py']
    identity = dict(version=VERSION, rows=rows,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))},
        external_files=external, math_runtime=proof.math_proof.math_proof()['runtime'], scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    atomic(out/'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def bound(out):
    identity = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or identity['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in identity['inputs'].items())
            or any(sha(Path(n)) != h for n, h in identity['external_files'].items())
            or identity['math_runtime'] != proof.math_proof.math_proof()['runtime']
            or identity['rows'] != [retained(p)[0] for p in PROFILES]):
        raise ValueError('Retained MIM current-proof context changed')
    return identity


def run(out):
    identity = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain previous or partial MIM RC proof')
        atomic(out/'state.json', dict(status='verifying', qualified_phy=False))
        rows = []
        try:
            for row in identity['rows']:
                target = out/row['variant']
                target.mkdir()
                result = proof.certify(target, row['extraction'], row['macro'], ROOT/row['reference'], 5)
                if result['independent_terminal_current_witness']['runtime'] != identity['math_runtime']:
                    raise ValueError('Independent MIM proof runtime changed')
                rows.append(dict(row, rc_proof=result, retained_component_rc_qualified=True,
                                 bank_timing_qualified=False, qualified_phy=False))
                atomic(target/'summary.json', rows[-1])
            bound(out)
            report = dict(rows=rows, retained_component_rc_qualified=True,
                new_extraction_performed=False, original_artifacts_modified=False,
                numerical_models_changed=False, bank_timing_qualified=False,
                electrical_qualification_passed=False, qualified_phy=False, scope=SCOPE)
            report['files'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                if p.is_file() and p.name not in ('state.json', '.execution.lock')}
            atomic(out/'summary.json', report)
            atomic(out/'state.json', dict(status='complete', passed=True, qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json', dict(status='failed', error=str(error), qualified_phy=False))
            raise
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'campaign'))
    parser.add_argument('artifact', type=Path, nargs='?')
    args = parser.parse_args()
    if args.action == 'run' and args.artifact is None:
        parser.error('run requires the exact prepared artifact')
    if args.action != 'run' and args.artifact is not None:
        parser.error('prepare/campaign use the fixed retained component identities')
    artifact = args.artifact.resolve() if args.action == 'run' else prepare()
    print(artifact, flush=True)
    if args.action in ('run', 'campaign'):
        print(run(artifact), flush=True)
