#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Zero-code native gate with actual driver and all twenty TG component RC models."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter
import tg_component_bank_v23 as circuit
import probe_small_guard_bank_v19 as parent
import verify_small_guard_bank_v19 as baseline_proof
import recover_tg_component_rc_v8 as recovery
import measure_tg_component_rc_v8 as measurement

previous = recovery.producer
helper = previous.previous.previous.original
ROOT = previous.ROOT
VERSION = 'all-data-component-rc-native-tg-bank-zero-code-gate-v23.1'
CONTEXT = 'tg_component_bank_v23'
SCOPE = ('Complete 16-tap/32-fine native bank with actual verified buffer, fine-unit, driver and all twenty TG component RC; '
         'all 903 MOS, 93 fine gates and 40 actual TG gates observed; zero-code SS/40 C gate only, '
         'SC control/common/tail-cap wiring remains unextracted; no whole-bank RC, complete sparse range, dense-code, '
         'code-update, periodic-duty, all-PVT, electrical or PHY qualification')


def specifications():
    return [s for s in parent.specifications() if s['coarse'] == s['fine'] == 0]


def libraries(evidence, tg_evidence):
    receipt = json.loads((evidence/'summary.json').read_text()); binding = receipt['identity']
    baseline_parent = ROOT/binding['parent']
    if (evidence.parent != ROOT/'build/diagnostics'/baseline_proof.CONTEXT or binding['version'] != baseline_proof.VERSION
            or evidence.name != hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
            or not receipt['all_consumed_complete_native_waveforms_verified'] or receipt['qualified_phy']
            or binding['case_ids'] != ['0', '1'] or len(receipt['rows']) != 2
            or any(helper.sha(ROOT/n) != h for n, h in binding['inputs'].items())):
        raise ValueError('Require the exact independently verified two complete passing zero-code cases')
    pm = parent.bound(baseline_parent); baseline = pm['identity']
    regenerated = parent.libraries(ROOT/baseline['evidence'], ROOT/baseline['network_evidence'])
    old_cells, old_banks, old_devices, old_gates, old_changes, paths, pdk_files, original = regenerated
    if (old_devices != baseline['devices'] or old_gates != baseline['fine_control_gates']
            or old_changes != baseline['changes'] or pdk_files != baseline['pdk_files'] or original != baseline['parent']
            or any(old_cells[p] != (baseline_parent/f'cells_{p}.spice').read_text()
                   or old_banks[p] != (baseline_parent/f'bank_{p}.spice').read_text() for p in circuit.PROFILES)):
        raise ValueError('Original actual-driver component bank cannot be regenerated')
    for row in receipt['rows']:
        task = row['task']; folder = baseline_parent/task['id']; profile = task['spec']['profile']
        original_row = json.loads((folder/'summary.json').read_text())
        if (task != pm['tasks'][int(task['id'])] or task['spec']['coarse'] != 0 or task['spec']['fine'] != 0
                or original_row['error'] is not None or original_row['result'] != row['result']
                or parent.measure(folder, task['spec'], old_devices[profile], old_gates[profile]) != row['result']
                or not all(row['result'][k] for k in ('terminal_screen_passed', 'control_settling_passed', 'onehot_control_settling_passed'))
                or row['result']['zero_code_fast_quarter_headroom_ps'] <= 0
                or any(v > 20 for v in row['result']['repeated_delay_difference_ps'].values())):
            raise ValueError('Original native zero-code baseline changed or failed')
    tg, tg_paths, provenance = circuit.witnesses(tg_evidence); paths += tg_paths
    cells = {}; banks = {}; devices = {}; gates = {}; changes = {}; tg_gates = {}
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in circuit.controls.dimensions.ports()}
    for profile in circuit.PROFILES:
        c, b, change = circuit.transform(old_cells[profile], old_banks[profile], tg, profile)
        ds = helper.circuit.native.mapped_mos(c+b, circuit.name(profile), mapping, 'XD')
        if (len(ds) != 903 or len({d['name'] for d in ds}) != 903
                or Counter((d['model'], d['limit_v']) for d in ds)
                != Counter((d['model'], d['limit_v']) for d in old_devices[profile])):
            raise ValueError('TG RC substitution changed native coverage or voltage limits')
        g = circuit.gate_observations(tg, b); mapped = {d['name']: d for d in ds}
        if len(g) != 40 or any(x['device'] not in mapped or mapped[x['device']]['terminals'][1] != x['gate_node'] for x in g+old_gates[profile]):
            raise ValueError('Actual fine/TG control-gate coverage failed')
        cells[profile] = c; banks[profile] = b; devices[profile] = ds; gates[profile] = old_gates[profile]; tg_gates[profile] = g
        changes[profile] = dict(old_changes[profile], **change, tg_provenance=provenance)
    paths += [evidence/'summary.json', *[ROOT/n for n in binding['inputs']]]
    paths += [baseline_parent/'manifest.json', *[baseline_parent/n for n in pm['libraries']]]
    return cells, banks, devices, gates, changes, paths, pdk_files, str(baseline_parent.relative_to(ROOT)), tg_gates


def fixture(out, spec, devices):
    text = parent.fixture(out, spec, devices)
    title = 'OpenLVDS '+parent.VERSION+'\n'; instance = ' '+parent.circuit.name(spec['profile'])+'\n'
    if not text.startswith(title) or text.count(instance) != 1:
        raise ValueError('Matched actual-TG native fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):].replace(instance, ' '+circuit.name(spec['profile'])+'\n', 1)


def measure(folder, spec, devices, gates, tg_gates):
    result = parent.measure(folder, spec, devices, gates)
    if len(tg_gates) != 40:
        raise ValueError('Require every actual TG control gate')
    requested = {'v('+g['gate_node'].replace(':', '.').lower()+')' for g in tg_gates}
    names, w = circuit.validate(folder/'bench.raw', requested, 20e-9)
    tg_controls = circuit.gate_measurements(names, w, tg_gates, spec)
    original = result['control_settling_passed']; internal = all(g['passed'] for g in tg_controls)
    result.update(scope=SCOPE, native_tg_controls=tg_controls, actual_tg_control_settling_passed=internal,
                  public_and_fine_controls_passed=original, control_settling_passed=bool(original and internal),
                  tg_component_parasitics_retained=True, all_data_component_parasitics_retained=True,
                  new_tg_junction_geometry='Actual independently verified PCell/GDS junctions and TG component RC',
                  whole_bank_rc_retained=False, physical_parasitics_retained=False,
                  electrical_qualification_passed=False, qualified_phy=False)
    return result


def prepare(evidence, tg_evidence):
    if helper.engine() != 'ngspice':
        raise ValueError('Require pinned native ngspice')
    cells, banks, devices, gates, changes, paths, pdk_files, baseline, tg_gates = libraries(evidence, tg_evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    cad = changes[next(iter(circuit.PROFILES))]['component_provenance']['cad_python']
    tg_cad = changes[next(iter(circuit.PROFILES))]['tg_provenance']['cad_python']
    if tg_cad['path'] == cad['path'] and tg_cad['sha256'] != cad['sha256']:
        raise ValueError('CAD interpreter witnesses disagree')
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), tg_evidence=str(tg_evidence.relative_to(ROOT)), parent=baseline,
                    external_files={cad['path']: cad['sha256'], tg_cad['path']: tg_cad['sha256']},
                    inputs={str(p.relative_to(ROOT)): helper.sha(p) for p in paths}, pdk_files=pdk_files,
                    simulator=helper.provenance(), devices=devices, fine_control_gates=gates, tg_control_gates=tg_gates, changes=changes,
                    specs=specifications(), max_workers=2, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    for profile in circuit.PROFILES:
        helper.write(out/f'cells_{profile}.spice', cells[profile]); helper.write(out/f'bank_{profile}.spice', banks[profile])
    tasks = []
    for n, spec in enumerate(identity['specs']):
        folder = out/str(n); folder.mkdir()
        helper.write(folder/'bench.cir', fixture(out, spec, devices[spec['profile']]))
        tasks.append(dict(id=str(n), spec=spec, deck_sha256=helper.sha(folder/'bench.cir')))
    helper.atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
                  libraries={p.name: helper.sha(p) for p in out.glob('*.spice')}, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['max_workers'] != 2
            or any(len(i['devices'][p]) != 903 or len(i['fine_control_gates'][p]) != 93 or len(i['tg_control_gates'][p]) != 40 for p in circuit.PROFILES)
            or set(m['libraries']) != {f'{kind}_{profile}.spice' for kind in ('cells', 'bank') for profile in circuit.PROFILES}
            or helper.engine() != 'ngspice' or helper.provenance() != i['simulator']
            or any(helper.sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(helper.sha(Path(n)) != h for n, h in i['pdk_files'].items())
            or any(helper.sha(Path(n)) != h for n, h in i['external_files'].items())
            or any(helper.sha(out/n) != h for n, h in m['libraries'].items()) or len(m['tasks']) != len(i['specs'])):
        raise ValueError('Native driver/selector context changed')
    for n, task in enumerate(m['tasks']):
        if (task['id'] != str(n) or task['spec'] != i['specs'][n]
                or helper.sha(out/str(n)/'bench.cir') != task['deck_sha256']
                or (out/str(n)/'bench.cir').read_text() != fixture(out, task['spec'], i['devices'][task['spec']['profile']])):
            raise ValueError('Native driver/selector task changed')
    return m


def run(out):
    m = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior native driver/selector campaign')
        helper.atomic(out/'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out/task['id']; result = error = wall = None; profile = task['spec']['profile']
            try:
                with helper.lease(ROOT, priority=0, label=CONTEXT+'_'+task['id']):
                    bound(out); start = time.monotonic()
                    p = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'), '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                    wall = time.monotonic()-start
                helper.write(folder/'console.log', p.stdout+p.stderr); p.check_returncode()
                result = measure(folder, task['spec'], m['identity']['devices'][profile], m['identity']['fine_control_gates'][profile], m['identity']['tg_control_gates'][profile])
            except Exception as e:
                error = str(e)
            row = dict(task=task, result=result, error=error, solver_wall_seconds=wall,
                       files={p.name: helper.sha(p) for p in folder.iterdir() if p.is_file()})
            helper.atomic(folder/'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, m['tasks']))
        bound(out); helper.atomic(out/'summary.json', dict(rows=rows, qualified_phy=False, scope=SCOPE))
        helper.atomic(out/'state.json', dict(status='complete', cases=len(rows), errors=sum(r['error'] is not None for r in rows), qualified_phy=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path)
    p.add_argument('--tg', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        if a.tg is None:
            p.error('Provide the independently verified actual TG component RC')
        print(prepare(a.artifact.resolve(), a.tg.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
