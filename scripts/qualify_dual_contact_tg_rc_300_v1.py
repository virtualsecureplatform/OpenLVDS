#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Apply current native/Schur proofs to fresh dual-contact coarse-TG RC."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import build_dual_contact_tg_300_v3 as cell
import verify_dual_contact_tg_300_v1 as verifier
import build_parallel_output_cell_v111 as proof
import native_bank_inventory_v51 as inventory
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit

ROOT = cell.ROOT
VERSION = 'dual-contact-tg-native-schur-component-proof-300-v1'
CONTEXT = 'dual_contact_tg_rc_proof_300_v1'
PROFILES = (('dual_contact',cell,'dual_contact_tg_300_v3/aeb4d8e09b8fdc6f',
             None),)
PORTS = cell.PORTS
SCOPE = ('Native geometry, exact reduction, passivity and independent Schur terminal-current proof '
         'for the dual-contact coarse TG only; no bank timing, PVT or PHY admission')


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
    label, module, artifact, _ = profile
    parent = ROOT/'build/diagnostics'/artifact
    receipt = verifier.verify(parent)
    verifier.bound(receipt)
    i, r = verifier.checked(parent)
    info = r['extraction']
    text = module.checked_netlist(info)
    ports, devices = inventory.native_leaves(collapse(text), module.NAME)
    if (ports != PORTS or dict(Counter(d['model'] for d in devices)) != {cell.N:1,cell.P:1}):
        raise ValueError('Dual-contact TG native inventory changed')
    paths = [receipt/'manifest.json',receipt/'summary.json']
    paths += [parent/n for n in ('manifest.json','summary.json','state.json')]
    paths += [ROOT/n for n in i['code']]
    paths += [parent/n for n in r['files']]
    paths += [ROOT/info[k] for k in ('raw_netlist','netlist')]
    paths += [ROOT/n for n in json.loads((receipt/'manifest.json').read_text())['identity']['inputs']]
    return dict(variant=label, macro=module.NAME, extraction=info,
                reference=str((parent/(module.NAME+'.lvs.spice')).relative_to(ROOT)),
                original_native_mos=2, original_native_mims=0,
                original_drc_count='0', original_lvs_passed=True), paths, i['external_files']


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
                result = proof.certify(target, row['extraction'], row['macro'], ROOT/row['reference'], 2)
                if result['independent_terminal_current_witness']['runtime'] != identity['math_runtime']:
                    raise ValueError('Independent MIM proof runtime changed')
                rows.append(dict(row, rc_proof=result, component_rc_qualified=True,
                                 bank_timing_qualified=False, qualified_phy=False))
                atomic(target/'summary.json', rows[-1])
            bound(out)
            report = dict(rows=rows, component_rc_qualified=True,
                new_extraction_performed=False, original_artifacts_modified=False,
                native_model_modified_by_proof=False, bank_timing_qualified=False,
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
