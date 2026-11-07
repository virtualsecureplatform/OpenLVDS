#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh native distributed RC of the physical P10/N8 -> P20/N16 buffer."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import build_request_taper_buffer_v323 as physical
import build_parallel_output_cell_v111 as proof
import extract_native_flat_v4 as extractor

ROOT = physical.ROOT
NAME = physical.NAME
VERSION = 'request-taper-buffer-full-native-local-rc-and-independent-schur-proof-v324.1'
CONTEXT = 'request_taper_buffer_rc_v324'
SCOPE = ('Fresh complete two-inverter REQUEST-buffer GDS-derived RC including actual new '
         'interstage and supply wires; native parameters/topology, passivity, exact reduction '
         'and independent Schur proof only, no transient/counter/shared-wire/PVT/PHY admission')
sha = physical.sha
atomic = physical.atomic


def checked(parent):
    identity = physical.bound(parent)
    report = json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or report.get('request_buffer_physical_passed') is not True
            or report['physical']['passed'] is not True or report['physical']['drc_count'] != '0'
            or report['physical']['lvs_passed'] is not True
            or report['native_mos'] != 54 or report['native_mims'] != 2
            or report['native_parameters']['native_primitives'] != 56
            or report['native_parameters']['newly_characterized_junction_devices'] != 0
            or any(sha(parent/n) != h for n, h in report['files'].items())):
        raise ValueError('Require the exact complete passing native REQUEST-buffer layout')
    gds = ROOT/report['physical']['gds']
    if sha(gds) != report['gds_sha256'] or sha(gds.with_suffix('.lef')) != report['lef_sha256']:
        raise ValueError('Qualified REQUEST-buffer GDS/LEF changed')
    if physical.native_witness(gds, identity['stages'], identity['plan']) != report['native_master_witness']:
        raise ValueError('Native REQUEST-buffer mask/placement witness changed')
    return identity, report, gds


def prepare(parent):
    previous, report, gds = checked(parent)
    paths = [parent/n for n in ('manifest.json', 'summary.json', 'state.json', *report['files'])]
    paths += [ROOT/n for n in previous['inputs']]
    paths += [ROOT/'scripts/exact_rc_candidate.py']
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)),
        gds=str(gds.relative_to(ROOT)), ports=report['ports'],
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
            or identity['tools'] != physical.small.primitive.environment.tools()
            or identity['math_runtime'] != proof.math_proof.math_proof()['runtime']):
        raise ValueError('REQUEST-buffer local-RC qualification context changed')
    checked(ROOT/identity['parent'])
    return identity


def run(out):
    identity = bound(out)
    parent = ROOT/identity['parent']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain previous or partial REQUEST-buffer RC qualification')
        atomic(out/'state.json', dict(status='extracting', qualified_phy=False))
        try:
            gds = ROOT/identity['gds']
            digest = hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()[:16]
            if (ROOT/'build/extracted'/digest/NAME).exists():
                raise ValueError('Retain existing or partial REQUEST-buffer extraction')
            native = gds.parent
            info = extractor.extract(NAME, gds, sha(out/'manifest.json'), ports=identity['ports'],
                source_scope=sha(native/(NAME+'.sch.spice')))
            atomic(out/'extraction.json', info)
            if not info['passed'] or info['ports_verified'] is not True or info['ports'] != physical.PORTS:
                raise ValueError('Fresh REQUEST-buffer RC extraction or public interface failed')
            target = out/'proof'
            target.mkdir()
            result = proof.certify(target, info, NAME, native/(NAME+'.lvs.spice'), 56)
            if result['independent_terminal_current_witness']['runtime'] != identity['math_runtime']:
                raise ValueError('Independent REQUEST-buffer math runtime changed')
            bound(out)
            report = dict(extraction=info, rc_proof=result, request_buffer_local_rc_qualified=True,
                native_mos=54, native_mims=2, actual_interstage_wire_rc_included=True,
                counter_timing_qualified=False, whole_counter_shared_wire_rc_qualified=False,
                all_pvt_covered=False, electrical_qualification_passed=False, qualified_phy=False, scope=SCOPE)
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
