#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract and certify local RC from the passed native 5x5 capacitor GDS."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import build_counter_output_mim5_v336 as physical
import build_parallel_output_cell_v111 as proof
import extract_native_flat_v4 as extractor

ROOT = physical.ROOT
NAME = physical.NAME
VERSION = 'native-counter-output-5x5-mim-gds-local-rc-schur-proof-v337.1'
CONTEXT = 'counter_output_mim5_rc_v337'
SCOPE = ('Fresh actual native 5x5 MIM component GDS-derived distributed RC, native '
         'parameters/topology, passivity, exact reduction and independent Schur proof; '
         'no counter placement/wiring/shared-RC, transient/PVT/DLL/PHY admission')
sha = physical.sha
atomic = physical.atomic


def require_physical(state, report):
    p = report.get('physical', {})
    n = report.get('native_inventory', {})
    if (state != dict(status='complete', passed=True, qualified_phy=False)
            or report.get('passed') is not True or p.get('passed') is not True
            or p.get('drc_count') != '0' or p.get('lvs_passed') is not True
            or (report.get('native_mos'), report.get('native_mim')) != (0, 1)
            or n.get('native_primitives') != 1
            or n.get('native_model_counts') != {physical.CAP: 1}
            or n.get('all_native_model_dimensions_preserved') is not True
            or n.get('native_parameters_preserved') is not True
            or report.get('native_labels') != dict(all_native_labels_preserved=True, native_text_records=2)
            or any(report.get(k, {}).get('all_native_masks_preserved') is not True
                   for k in ('native_masks', 'whole_masks'))
            or list(report.get('plan', {}).get('ports', {})) != physical.PORTS):
        raise ValueError('Require the complete passing native 5x5 capacitor physical material')


def checked(parent):
    manifest = physical.bound(parent)
    report = json.loads((parent/'summary.json').read_text())
    require_physical(json.loads((parent/'state.json').read_text()), report)
    if any(sha(parent/n) != h for n, h in report['files'].items()):
        raise ValueError('Qualified native capacitor physical files changed')
    gds = parent/(NAME+'.gds')
    if str(gds.relative_to(ROOT)) != report['physical']['gds']:
        raise ValueError('Qualified native capacitor GDS path changed')
    return manifest['identity'], report, gds


def prepare(parent):
    previous, report, gds = checked(parent)
    paths = [parent/n for n in ('manifest.json', 'summary.json', 'state.json', *report['files'])]
    paths += [ROOT/n for n in previous['inputs']]
    paths += [ROOT/'scripts/exact_rc_candidate.py']
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)),
        gds=str(gds.relative_to(ROOT)), ports=report['plan']['ports'],
        inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))},
        external_files=previous['external_files'], tools=previous['tools'],
        math_runtime=proof.math_proof.math_proof()['runtime'], scope=SCOPE)
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
            or identity['tools'] != physical.environment.tools()
            or identity['math_runtime'] != proof.math_proof.math_proof()['runtime']
            or identity['scope'] != SCOPE):
        raise ValueError('Native capacitor local-RC qualification context changed')
    _, report, gds = checked(ROOT/identity['parent'])
    if identity['ports'] != report['plan']['ports'] or identity['gds'] != str(gds.relative_to(ROOT)):
        raise ValueError('Native capacitor local-RC electrodes changed')
    return identity


def run(out):
    identity = bound(out)
    parent = ROOT/identity['parent']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain previous or partial native capacitor RC qualification')
        atomic(out/'state.json', dict(status='extracting', qualified_phy=False))
        try:
            gds = ROOT/identity['gds']
            digest = hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()[:16]
            if (ROOT/'build/extracted'/digest/NAME).exists():
                raise ValueError('Retain existing or partial native capacitor extraction')
            info = extractor.extract(NAME, gds, sha(out/'manifest.json'), ports=identity['ports'],
                source_scope=sha(parent/(NAME+'.sch.spice')))
            atomic(out/'extraction.json', info)
            if not info['passed'] or info['ports_verified'] is not True or info['ports'] != physical.PORTS:
                raise ValueError('Fresh native capacitor RC extraction or public interface failed')
            target = out/'proof'
            target.mkdir()
            result = proof.certify(target, info, NAME, parent/(NAME+'.lvs.spice'), 1)
            if result['independent_terminal_current_witness']['runtime'] != identity['math_runtime']:
                raise ValueError('Independent native capacitor math runtime changed')
            bound(out)
            report = dict(extraction=info, rc_proof=result, capacitor_local_rc_qualified=True,
                native_mos=0, native_mim=1, counter_timing_qualified=False,
                whole_counter_shared_wire_rc_qualified=False, all_pvt_covered=False,
                electrical_qualification_passed=False, qualified_phy=False, scope=SCOPE)
            report['files'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                if p.is_file() and p.name not in ('state.json', '.execution.lock')}
            report['extracted_files'] = {info[k]: sha(ROOT/info[k]) for k in ('raw_netlist', 'netlist')}
            atomic(out/'summary.json', report)
            atomic(out/'state.json', dict(status='complete', passed=True, qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json', dict(status='failed', error=str(error), qualified_phy=False))
            raise
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'campaign'))
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if args.action in ('prepare', 'campaign'):
        artifact = prepare(artifact)
        print(artifact, flush=True)
    if args.action in ('run', 'campaign'):
        print(run(artifact), flush=True)
