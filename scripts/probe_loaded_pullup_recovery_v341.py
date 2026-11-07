#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test qualified P40/N16 recovery against the completed P20/P24 native replay."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_loaded_fine_recovery_v333 as source
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT = source.ROOT
VERSION = 'recorded-native-fine-stage-p40-pullup-only-recovery-intervention-v341.1'
CONTEXT = 'loaded_pullup_recovery_v341'
TOP = 'openlvds_replayed_pullup_fine_v341'
MODEL = 'openlvds_recovery_p40n16_v339'
VARIANT = 'p40'
sha = source.sha
atomic = source.atomic
SCOPE = ('Actual unchanged v333 selected-node PWL and retained 31-cell fine stage; '
         'only the loaded inverter becomes qualified native P40/N16 local RC; all '
         'eight startup events retained; no upstream loading, quarter latency, '
         'coarse/fine range, whole-bank shared-RC/PVT/DLL/PHY admission')


def transform(bank, previous, cell):
    native = source.source.source.native
    definition = source.source.source.cell_definition
    defs = native.definitions(bank)
    extra = native.definitions(cell)
    if set(extra) != {MODEL} or extra[MODEL][0] != ['A', 'Y', 'VGND', 'VPWR'] or MODEL in defs:
        raise ValueError('Require the exact qualified native P40/N16 interface and namespace')
    before = definition(bank, source.TOP)
    old = ['Xfine_isolate', 'selected', 'fine_node', 'VGND', 'VPWR', source.MODELS['baseline']]
    if [w for w in defs[source.TOP][1] if w[0] == old[0]] != [old]:
        raise ValueError('Original replayed P20/N16 loaded inverter changed')
    # Distributed RC can hide a changed public pin behind unchanged internal
    # MOS node names. Check every retained top-level call as well as MOS maps.
    expected = [old, ['Xfine_regenerate1', 'fine_node', 'OUT', 'VGND', 'VPWR', source.MODELS['baseline']]]
    for k in range(31):
        expected += [[f'Xfine_buffer{k}', f'E{k}', 'VGND', 'VGND', 'VPWR', 'VPWR', f'fine{k}', 'sky130_fd_sc_hd__buf_1'],
                     [f'Xfine_inverse{k}', f'fine{k}', 'VGND', 'VGND', 'VPWR', 'VPWR', f'fine_b{k}', 'sky130_fd_sc_hd__inv_1'],
                     [f'Xfine_unit{k}', 'fine_node', f'fine{k}', f'fine_b{k}', 'VPWR', 'VGND',
                      'openlvds_measured_gangs_b2_v125_unit']]
    expected += [['Rboundary', 'selected', 'REPLAY', '1m']]
    if defs[source.TOP][1] != expected:
        raise ValueError('Non-loaded native terminals, top-level calls or replay boundary changed')
    after = before.replace(' '.join(old)+'\n', ' '.join(old[:-1]+[MODEL])+'\n', 1)
    after = after.replace('.subckt '+source.TOP+' ', '.subckt '+TOP+' ', 1)
    after = after.replace('.ends '+source.TOP+'\n', '.ends '+TOP+'\n', 1)
    result = bank.replace(before, after, 1)+'\n'+cell
    if any(definition(result, n) != definition(bank, n) for n in defs if n != source.TOP):
        raise ValueError('Unrelated qualified native component changed')
    ports = defs[source.TOP][0]
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = native.mapped_mos(result, TOP, pins, 'XD')
    old_devices = {d['name']: d for d in previous['devices']}
    new = {d['name']: d for d in devices}
    prefix = 'XD:Xfine_isolate:'
    if (len(old_devices) != 413 or len(new) != len(devices) or len(new) != 433
            or sum(n.startswith(prefix) for n in old_devices) != 36
            or sum(n.startswith(prefix) for n in new) != 56
            or any(new.get(n) != d for n, d in old_devices.items() if not n.startswith(prefix))):
        raise ValueError('Non-loaded native terminals or exact P40/N16 census changed')
    if len(previous['controls']) != 62 or len(previous['programming_gates']) != 93:
        raise ValueError('Incomplete retained fine-cell controls')
    if any(new[g['device']]['terminals'][1] != g['gate_node'] for g in previous['programming_gates']):
        raise ValueError('Retained native programming-gate map changed')
    return result, dict(devices=devices, controls=previous['controls'],
                        programming_gates=previous['programming_gates'])


def fixture(out, identity):
    text = source.fixture(out, identity, VARIANT)
    if text.count(source.TOP) != 1:
        raise ValueError('Original replay fixture top changed')
    return text.replace(source.TOP, TOP, 1).replace('OpenLVDS '+source.VERSION, 'OpenLVDS '+VERSION, 1)


def recovery_evidence(parent, evidence):
    manifest = source.bound(parent)
    identity = manifest['identity']
    report = json.loads((evidence/'summary.json').read_text())
    rows = [json.loads((parent/str(k)/'summary.json').read_text()) for k in range(2)]
    if (json.loads((parent/'state.json').read_text()) !=
            dict(status='complete', cases=2, errors=0, guarded=0, qualified_phy=False)
            or [r['task'] for r in rows] != manifest['tasks']
            or any(r['error'] is not None or r['guarded'] for r in rows)
            or not source.baseline_usable(rows[0]['result'])
            or report.get('case') != str((parent/'1').relative_to(ROOT))
            or report.get('native_mos') != 417
            or report.get('all_original_native_metrics_reproduced') is not True
            or report.get('baseline_independent_replay_bound') is not True
            or report.get('parameters_changed') is not False):
        raise ValueError('Require complete baseline parity and independently replayed P24 intervention')
    for row in rows:
        case = parent/row['task']['id']
        if any(sha(case/n) != h for n, h in row['files'].items()):
            raise ValueError('Retained native recovery trace changed')
        actual = source.measure(case, identity, row['task']['variant'])
        if row['task']['variant'] == 'baseline':
            actual['baseline_parity'] = source.parity(case, identity)
        if actual != row['result']:
            raise ValueError('Retained P20/P24 native metrics do not reproduce')
    if (report['comparison']['p24_maximum_period_error_ps'] != rows[1]['result']['maximum_period_error_ps']
            or rows[1]['result']['period_screen_passed'] is not False
            or any(sha(ROOT/n) != h for n, h in report['inputs'].items())):
        raise ValueError('P24 failed-intervention evidence changed')
    paths = [evidence/'summary.json', *[ROOT/n for n in report['inputs']],
             *[parent/n for n in ('manifest.json', 'summary.json', 'state.json', 'selected.spice')],
             *[parent/n for n in manifest['libraries']], *[ROOT/n for n in identity['inputs']]]
    for row in rows:
        case = parent/row['task']['id']
        paths += [case/'summary.json', *[case/n for n in row['files']]]
    return identity, rows, paths


def materials(parent):
    code = ('import sys;from pathlib import Path;sys.path.insert(0,"scripts");'
            'import qualify_recovery_fine_driver_rc_v340 as q;q.bound(Path(sys.argv[1]))')
    check = subprocess.run([source.drivers.CAD, '-c', code, str(parent)],
                           cwd=ROOT, capture_output=True, text=True)
    if check.returncode:
        raise ValueError('Native P40/N16 component RC context changed: '+check.stderr[-2000:])
    identity = json.loads((parent/'manifest.json').read_text())['identity']
    report = json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or report.get('recovery_driver_local_rc_qualified') is not True or len(report['rows']) != 1
            or any(sha(parent/n) != h for n, h in report['files'].items())
            or any(sha(ROOT/n) != h for n, h in report['extracted_files'].items())):
        raise ValueError('Require complete actual P40/N16 component RC')
    row = report['rows'][0]
    proof = row['rc_proof']
    if (row['macro'] != MODEL or row['spec'] != dict(p_fingers=40, n_fingers=16)
            or row['local_rc_qualified'] is not True
            or any(proof.get(k) is not True for k in
                   ('component_rc_passed', 'exact_reduction_regenerated', 'native_topology_verified'))
            or proof['independent_terminal_current_witness']['proof']['passed'] is not True):
        raise ValueError('Native P40/N16 topology, parameter or current proof failed')
    info = row['extraction']
    cell = source.source.source.cell_definition((ROOT/info['netlist']).read_text(), MODEL)
    paths = [parent/n for n in ('manifest.json', 'summary.json', 'state.json', *report['files'])]
    paths += [ROOT/n for n in {*identity['inputs'], *report['extracted_files']}]
    return cell, paths, identity


def prepare(parent, component, evidence):
    previous, rows, paths = recovery_evidence(parent, evidence)
    cell, files, material = materials(component)
    paths += files
    bank, observations = transform((parent/'baseline/bank.spice').read_text(), previous['observations']['baseline'], cell)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), materials=str(component.relative_to(ROOT)),
        evidence=str(evidence.relative_to(ROOT)), spec=previous['spec'], original_fixture=previous['original_fixture'],
        observations={VARIANT: observations}, inputs=inputs, guards=source.source.guard_inputs(inputs),
        simulator=previous['simulator'], pdk_files=previous['pdk_files'],
        external_files={**previous['external_files'], **material['external_files']},
        wave_sha256=previous['wave_sha256'], native_source_points=previous['native_source_points'],
        retained_comparison=dict(baseline=rows[0]['result'], p24=rows[1]['result']),
        max_workers=1, priority=1, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'selected.spice').write_bytes((parent/'selected.spice').read_bytes())
    library = out/VARIANT
    library.mkdir()
    (library/'bank.spice').write_text(bank)
    folder = out/'0'
    folder.mkdir()
    (folder/'bench.cir').write_text(fixture(out, identity))
    task = dict(id='0', variant=VARIANT, deck_sha256=sha(folder/'bench.cir'))
    atomic(out/'manifest.json', dict(identity=identity, tasks=[task],
        libraries={VARIANT+'/bank.spice': sha(library/'bank.spice')}, qualified_phy=False))
    return out


def bound(out, full=True):
    manifest = json.loads((out/'manifest.json').read_text())
    identity = manifest['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or identity['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or identity['scope'] != SCOPE or (identity['max_workers'], identity['priority']) != (1, 1)
            or identity['spec'] != source.source.specifications()[1]
            or identity['guards'] != source.source.guard_inputs(identity['inputs'])
            or any(sha(ROOT/n) != h for n, h in (identity['inputs'] if full else identity['guards']).items())
            or any(sha(Path(n)) != h for n, h in {**identity['pdk_files'], **identity['external_files']}.items())
            or engine() != 'ngspice' or provenance() != identity['simulator']
            or sha(out/'selected.spice') != identity['wave_sha256']
            or any(sha(out/n) != h for n, h in manifest['libraries'].items())):
        raise ValueError('Native P40 pull-up recovery context changed')
    text = (out/VARIANT/'bank.spice').read_text()
    original = (ROOT/identity['parent']/'baseline/bank.spice').read_text()
    cell = source.source.source.cell_definition(text, MODEL)
    expected, observations = transform(original,
        json.loads((ROOT/identity['parent']/'manifest.json').read_text())['identity']['observations']['baseline'], cell)
    if (text != expected or identity['observations'] != {VARIANT: observations}
            or (out/'0/bench.cir').read_text() != fixture(out, identity)
            or manifest['tasks'] != [dict(id='0', variant=VARIANT, deck_sha256=sha(out/'0/bench.cir'))]):
        raise ValueError('Native P40 recovery fixture, terminal map or single intervention changed')
    return manifest


def measure(folder, identity):
    result = source.measure(folder, identity, VARIANT)
    result.update(scope=SCOPE, full_bank_qualified=False, qualified_phy=False)
    return result


def run(out):
    manifest = bound(out)
    identity = manifest['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain any prior or partial native P40 recovery execution')
        atomic(out/'state.json', dict(status='running', qualified_phy=False))
        folder = out/'0'
        result = error = None
        try:
            with lease(ROOT, priority=1, label=CONTEXT+'_0'):
                bound(out, full=False)
                process = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'),
                    '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
            (folder/'console.log').write_text(process.stdout+process.stderr)
            process.check_returncode()
            result = measure(folder, identity)
        except Exception as exception:
            error = str(exception)
        row = dict(task=manifest['tasks'][0], result=result, error=error,
            files={p.name: sha(p) for p in folder.iterdir() if p.is_file()})
        atomic(folder/'summary.json', row)
        bound(out)
        atomic(out/'summary.json', dict(rows=[row], full_bank_qualified=False, qualified_phy=False, scope=SCOPE))
        atomic(out/'state.json', dict(status='complete', cases=1, errors=int(error is not None), qualified_phy=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    prepare_parser = actions.add_parser('prepare')
    for key in ('parent', 'materials', 'evidence'):
        prepare_parser.add_argument(key, type=Path)
    actions.add_parser('run').add_argument('artifact', type=Path)
    args = parser.parse_args()
    print(prepare(args.parent.resolve(), args.materials.resolve(), args.evidence.resolve())
          if args.action == 'prepare' else run(args.artifact.resolve()), flush=True)
