#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare two qualified smaller first restorers with unchanged bank native gates."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import probe_regular_regenerated_bank_v263 as source
from audit_rc_comments_v2 import collapse
from build_compound_drivers_v3 import cell_definition
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT = source.ROOT
sha = source.sha
VERSION = 'smaller-first-restorer-native-bank-latency-and-overlap-v310.1'
CONTEXT = 'tapered_regenerated_bank_v310'
TOP = 'openlvds_tapered_regenerated_fine_v310'
MODELS = {'p6n4': 'openlvds_tapered_p6n4_v308',
          'p10n8': 'openlvds_tapered_p10n8_v308'}
COUNTS = {'p6n4': 1503, 'p10n8': 1511}
CAD = source.source.CAD
SCOPE = ('Qualified smaller first restoration inverter only; original isolation, final P20/N16, '
         'coarse/fine bank, controls and all eight native startup cycles retained; component RC '
         'with ideal new shared wires, no routed/dense/update/all-PVT/DLL/PHY admission')


def specifications():
    return [dict(s, first_restorer=v, regenerator=v + '_then_p20n16')
            for v in MODELS for s in source.specifications()]


def transform(bank, previous, cells, variant):
    if variant not in MODELS:
        raise ValueError('Unknown tapered restoration variant')
    model = MODELS[variant]
    original = source.native.definitions(bank)
    added = source.native.definitions(cells)
    if model in original or set(added) != {model} or added[model][0] != ['A', 'Y', 'VGND', 'VPWR']:
        raise ValueError('Qualified smaller driver namespace or port order changed')
    old = ['Xfine_regenerate0', 'fine_node', 'restored_b', 'VGND', 'VPWR', source.MODEL]
    final = ['Xfine_regenerate1', 'restored_b', 'OUT', 'VGND', 'VPWR', source.MODEL]
    body = original[source.TOP][1]
    if ([w for w in body if w[0] == old[0]] != [old]
            or [w for w in body if w[0] == final[0]] != [final]):
        raise ValueError('Original first/final restoration topology changed')
    before = cell_definition(bank, source.TOP)
    after = before.replace(' '.join(old) + '\n', ' '.join(old[:-1] + [model]) + '\n', 1)
    after = after.replace('.subckt ' + source.TOP + ' ', '.subckt ' + TOP + ' ', 1)
    after = after.replace('.ends ' + source.TOP + '\n', '.ends ' + TOP + '\n', 1)
    result = bank.replace(before, after, 1) + '\n' + cells
    for name in original:
        if name != source.TOP and cell_definition(result, name) != cell_definition(bank, name):
            raise ValueError('Unrelated native macro changed')
    ports = original[source.TOP][0]
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = source.native.mapped_mos(result, TOP, pins, 'XD')
    old_devices = {d['name']: d for d in previous['devices']}
    new_devices = {d['name']: d for d in devices}
    prefix = 'XD:Xfine_regenerate0:'
    removed = {n for n in old_devices if n.startswith(prefix)}
    if (len(removed) != 36 or len(devices) != COUNTS[variant]
            or len(new_devices) != len(devices)
            or any(new_devices.get(n) != d for n, d in old_devices.items() if n not in removed)):
        raise ValueError('Non-first-restorer terminal maps or exact native MOS census changed')
    if any(c['node'].startswith(prefix) for c in previous['controls']):
        raise ValueError('Stale first-restorer control observation')
    gates = [dict(g, gate_node=new_devices[g['device']]['terminals'][1])
             for g in previous['programming_gates']]
    if gates != previous['programming_gates'] or len(gates) != 173 or len(previous['controls']) != 86:
        raise ValueError('Typed programming gates or logical controls changed')
    _, leaves = source.inventory.native_leaves(collapse(result), TOP)
    counts = {k: sum(('fet_' in d['model']) == k for d in leaves) for k in (True, False)}
    if counts != {True: COUNTS[variant], False: 43}:
        raise ValueError('Native MOS/MIM inventory changed')
    observations = dict(devices=devices, controls=previous['controls'], programming_gates=gates)
    proof = dict(native_mos=COUNTS[variant], native_mims=43, removed_first_restorer_mos=36,
                 added_first_restorer_mos=COUNTS[variant] - 1493,
                 all_other_native_terminal_maps_preserved=True,
                 all_unrelated_macro_definitions_preserved=True,
                 all_typed_programming_gates_preserved=True,
                 shared_wire_rc_qualified=False, qualified_phy=False)
    return result, observations, proof


def fixture(out, identity, spec):
    variant = spec['first_restorer']
    local = dict(identity, observations=identity['observations'][variant])
    text = source.fixture(out / variant, local, spec)
    if text.count(source.TOP) != 1:
        raise ValueError('Original native fixture top changed')
    text = text.replace(source.TOP, TOP, 1)
    return text.replace('OpenLVDS ' + source.VERSION + '\n', 'OpenLVDS ' + VERSION + '\n', 1)


def require_baseline(parent, manifest):
    case = parent / '0'
    if not (case / 'summary.json').exists():
        raise ValueError('Wait for naturally completed original zero-code native case')
    row = json.loads((case / 'summary.json').read_text())
    if (row['task'] != manifest['tasks'][0] or row['spec'] != source.specifications()[0]
            or row['error'] is not None or row['result'] is None
            or not {'bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'} <= set(row['files'])
            or any(sha(case / n) != h for n, h in row['files'].items())):
        raise ValueError('Require complete unchanged native zero-code reference')
    result = source.measure(case, manifest['identity'], row['spec'])
    gates = ('all_input_output_pulses_present', 'input_timing_stimulus_passed',
             'full_swing_pulses_passed', 'unwrapped_native_epoch_passed',
             'pulse_order_and_widths_passed', 'period_screen_passed',
             'repeated_delay_screen_passed', 'terminal_screen_passed',
             'control_settling_passed', 'current_downstream_250ps_slew_domain_passed')
    if (result != row['result'] or result['zero_code_quarter_passed'] is not False
            or not all(result[k] is True for k in gates)):
        raise ValueError('Require independently reproduced isolated zero-quarter latency failure')
    return row, [case / 'summary.json', *[case / n for n in row['files']]]


def driver_materials(parent):
    code = ('import sys;from pathlib import Path;sys.path.insert(0,"scripts");'
            'import qualify_tapered_fine_driver_rc_v309 as p;p.bound(Path(sys.argv[1]))')
    checked = subprocess.run([CAD, '-c', code, str(parent)], cwd=ROOT, capture_output=True, text=True)
    if checked.returncode:
        raise ValueError('Qualified tapered driver RC changed: ' + checked.stderr[-2000:])
    manifest = json.loads((parent / 'manifest.json').read_text())
    identity = manifest['identity']
    report = json.loads((parent / 'summary.json').read_text())
    if (json.loads((parent / 'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or report.get('balanced_driver_local_rc_qualified') is not True
            or [r['macro'] for r in report['rows']] != list(MODELS.values())
            or any(sha(parent / n) != h for n, h in report['files'].items())
            or any(sha(ROOT / n) != h for n, h in report['extracted_files'].items())):
        raise ValueError('Require both complete unchanged qualified smaller driver RC networks')
    libraries = {}
    for variant, row in zip(MODELS, report['rows']):
        proof = row['rc_proof']
        if (row['local_rc_qualified'] is not True
                or any(proof[k] is not True for k in ('component_rc_passed', 'exact_reduction_regenerated', 'native_topology_verified'))
                or proof['independent_terminal_current_witness']['proof']['passed'] is not True):
            raise ValueError('Tapered driver native RC qualification failed')
        libraries[variant] = cell_definition((ROOT / row['extraction']['netlist']).read_text(), MODELS[variant])
    paths = [parent / n for n in ('manifest.json', 'summary.json', 'state.json', *report['files'])]
    paths += [ROOT / n for n in {*identity['inputs'], *report['extracted_files']}]
    return libraries, paths, identity


def prepare(parent, drivers):
    if not (parent / '0/summary.json').exists():
        raise ValueError('Wait for naturally completed original zero-code native case')
    manifest = source.bound(parent)
    baseline, baseline_paths = require_baseline(parent, manifest)
    cells, paths, driver_identity = driver_materials(drivers)
    previous = manifest['identity']
    if engine() != 'ngspice' or provenance() != previous['simulator']:
        raise ValueError('Require unchanged original native simulator')
    bank = (parent / 'bank.spice').read_text()
    libraries = {v: transform(bank, previous['observations'], cells[v], v) for v in MODELS}
    paths += baseline_paths + [parent / 'manifest.json', parent / 'bank.spice']
    paths += [ROOT / n for n in previous['inputs']]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT / 'scripts'})
    identity = dict(previous, version=VERSION, parent=str(parent.relative_to(ROOT)),
                    drivers=str(drivers.relative_to(ROOT)), specs=specifications(),
                    baseline_zero=baseline, observations={v: libraries[v][1] for v in MODELS},
                    native_revision={v: libraries[v][2] for v in MODELS},
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))},
                    external_files={**previous['external_files'], **driver_identity['external_files']},
                    max_workers=2, priority=1, scope=SCOPE)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT / 'build/diagnostics' / CONTEXT / digest
    out.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for variant in MODELS:
        folder = out / variant
        folder.mkdir()
        path = folder / 'bank.spice'
        path.write_text(libraries[variant][0])
        hashes[str(path.relative_to(out))] = sha(path)
    tasks = []
    for k, spec in enumerate(identity['specs']):
        folder = out / str(k)
        folder.mkdir()
        (folder / 'bench.cir').write_text(fixture(out, identity, spec))
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(folder / 'bench.cir')))
    atomic(out / 'manifest.json', dict(identity=identity, tasks=tasks, libraries=hashes, qualified_phy=False))
    return out


def bound(out):
    manifest = json.loads((out / 'manifest.json').read_text())
    identity = manifest['identity']
    if (out.parent != ROOT / 'build/diagnostics' / CONTEXT or identity['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or identity['specs'] != specifications() or identity['max_workers'] != 2 or identity['priority'] != 1
            or engine() != 'ngspice' or provenance() != identity['simulator']
            or any(sha(ROOT / n) != h for n, h in identity['inputs'].items())
            or any(sha(Path(n)) != h for n, h in {**identity['pdk_files'], **identity['external_files']}.items())
            or set(manifest['libraries']) != {v + '/bank.spice' for v in MODELS}
            or any(sha(out / n) != h for n, h in manifest['libraries'].items())
            or len(manifest['tasks']) != 8):
        raise ValueError('Tapered restoration native campaign changed')
    for k, task in enumerate(manifest['tasks']):
        path = out / str(k) / 'bench.cir'
        if (task != dict(id=str(k), spec=identity['specs'][k], deck_sha256=sha(path))
                or path.read_text() != fixture(out, identity, task['spec'])):
            raise ValueError('Original eight-cycle native stimulus or observations changed')
    return manifest


def measure(folder, identity, spec):
    local = dict(identity, observations=identity['observations'][spec['first_restorer']])
    result = source.measure(folder, local, spec)
    return dict(result, whole_bank_rc_retained=False, new_common_routing_qualified=False,
                electrical_qualification_passed=False, qualified_phy=False, scope=SCOPE)


def compare(rows):
    if len(rows) != 8 or any(r['error'] is not None or r['result'] is None for r in rows):
        return None
    if [r['spec'] for r in rows] != specifications():
        raise ValueError('Require both variants and complete zero/duty-endpoint/coarse coverage')
    comparisons = {}
    for variant in MODELS:
        group = [r for r in rows if r['spec']['first_restorer'] == variant]
        valid = all(len(r['result']['edge_delays_ps'][e]) == 8
                    and all(np.isfinite(v) and v > 0 for v in r['result']['edge_delays_ps'][e])
                    for r in group for e in ('rise', 'fall'))
        overlap = {e: min(v for r in group[1:3] for v in r['result']['edge_delays_ps'][e])
                   - max(group[3]['result']['edge_delays_ps'][e]) if valid else None
                   for e in ('rise', 'fall')}
        comparisons[variant] = dict(
            component_hypothesis_passed=bool(valid and all(r['result']['current_clock_interface_screen_passed'] for r in group)
                                           and all(v > 0 for v in overlap.values())),
            zero_quarter_headroom_ps=group[0]['result']['zero_code_fast_quarter_headroom_ps'],
            conservative_coarse_overlap_ps=overlap)
    return dict(variants=comparisons, complete_native_component_comparison=True,
                shared_wire_rc_qualified=False, all_pvt_covered=False,
                electrical_qualification_passed=False, qualified_phy=False)


def run(out):
    manifest = bound(out)
    identity = manifest['identity']
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists():
            raise ValueError('Retain previous or partial tapered restoration campaign')
        atomic(out / 'state.json', dict(status='running', qualified_phy=False))

        def execute(task):
            folder = out / task['id']
            result = error = None
            try:
                with lease(ROOT, priority=identity['priority'], label=CONTEXT + '_' + task['id']):
                    bound(out)
                    process = subprocess.run([sys.executable, str(ROOT / 'scripts/run_native_binary_v2.py'),
                                              '-l', str(folder / 'ngspice.log'), str(folder / 'bench.cir')],
                                             capture_output=True, text=True)
                (folder / 'console.log').write_text(process.stdout + process.stderr)
                process.check_returncode()
                result = measure(folder, identity, task['spec'])
            except Exception as exception:
                error = str(exception)
            row = dict(task=task, spec=task['spec'], result=result, error=error,
                       files={p.name: sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder / 'summary.json', row)
            return row

        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, manifest['tasks']))
        bound(out)
        atomic(out / 'summary.json', dict(rows=rows, comparison=compare(rows), scope=SCOPE, qualified_phy=False))
        atomic(out / 'state.json', dict(status='complete', cases=8,
                                       errors=sum(r['error'] is not None for r in rows), qualified_phy=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'campaign'])
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--drivers', type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if args.action in ('prepare', 'campaign'):
        if args.drivers is None:
            parser.error('--drivers required')
        artifact = prepare(artifact, args.drivers.resolve())
        print(artifact, flush=True)
    if args.action in ('run', 'campaign'):
        print(run(artifact), flush=True)
