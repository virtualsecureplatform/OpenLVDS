#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Legal NMOS-low-Vt isolation with every original component R/C retained."""
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
import nlvt_data_path_v25 as circuit
import probe_tg_component_bank_v23 as source
import verify_tg_component_bank_v23 as baseline_proof
import recover_tg_component_rc_v8 as recovery
import measure_tg_component_rc_v8 as measurement

previous = recovery.producer
helper = previous.previous.previous.original
ROOT = previous.ROOT
VERSION = 'legal-nmos-low-vt-complete-reference-rc-zero-screen-v25.1'
CONTEXT = 'nlvt_data_path_v25'
SCOPE = ('Complete 16-tap/32-fine both3 bank, isolate legal L0.15 NMOS-low-Vt in TGs or TGs/drivers/coarse buffers; '
         'coarse-buffer HVT PMOS becomes regular at unchanged L0.15, no PMOS-LVT substitution; all original W/L, junction '
         'and R/C tokens retained but reference component RC is borrowed for changed implants; fine switches and control '
         'cells unchanged, all 903 MOS/93 fine/40 TG gates observed; zero SS/40 C only, no new physical equivalence, '
         'whole-bank RC, sparse-range/dense/PVT, code-update, periodic-duty, electrical or PHY qualification')


def specifications():
    return [dict(source.specifications()[1], profile=p) for p in circuit.PROFILES]


def libraries(evidence):
    receipt = json.loads((evidence/'summary.json').read_text()); binding = receipt['identity']; parent = ROOT/binding['parent']
    if (evidence.parent != ROOT/'build/diagnostics'/baseline_proof.CONTEXT
            or binding['version'] != baseline_proof.VERSION or not receipt['all_declared_cases_consumed']
            or receipt['qualified_phy'] or baseline_proof.verify(parent) != evidence):
        raise ValueError('Require complete independently verified failed actual-component-RC zero gate')
    pm = source.bound(parent); baseline = pm['identity']
    original = source.libraries(ROOT/baseline['evidence'], ROOT/baseline['tg_evidence'])
    old_cells, old_banks, old_devices, old_gates, old_changes, paths, pdk_files, previous_parent, old_tg_gates = original
    if (old_devices != baseline['devices'] or old_gates != baseline['fine_control_gates']
            or old_tg_gates != baseline['tg_control_gates'] or old_changes != baseline['changes']
            or previous_parent != baseline['parent'] or pdk_files != baseline['pdk_files']
            or any(old_cells[p] != (parent/f'cells_{p}.spice').read_text() or old_banks[p] != (parent/f'bank_{p}.spice').read_text() for p in source.circuit.PROFILES)):
        raise ValueError('Original failed component-RC bank cannot be regenerated')
    target = next(r['result'] for r in receipt['rows'] if r['task']['spec']['profile'] == 'both3')
    if target['zero_code_fast_quarter_headroom_ps'] >= 0 or not target['terminal_screen_passed'] or not target['control_settling_passed']:
        raise ValueError('Require timing-only failure at the best smaller-guard zero code')
    cells = {}; banks = {}; devices = {}; gates = {}; changes = {}; tg_gates = {}
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in source.circuit.controls.dimensions.ports()}
    def terminals(ds):return [(d['name'], d['terminals'], d['limit_v']) for d in ds]
    for profile in circuit.PROFILES:
        c, b, change = circuit.transform(old_cells['both3'], old_banks['both3'], profile)
        ds = helper.circuit.native.mapped_mos(c+b, circuit.name(profile), mapping, 'XD')
        if len(ds) != 903 or terminals(ds) != terminals(old_devices['both3']):
            raise ValueError('NMOS flavor isolation changed terminal coverage or voltage limits')
        differences = Counter((a['model'], b['model']) for a, b in zip(old_devices['both3'], ds) if a['model'] != b['model'])
        expected = Counter({(circuit.N, circuit.NLVT): change['native_nmos_model_changes']})
        if change['native_pmos_model_changes']:
            expected[circuit.PHVT, circuit.P] = change['native_pmos_model_changes']
        if differences != expected:
            raise ValueError('Unexpected native device-flavor change')
        mapped = {d['name']: d for d in ds}; g = old_tg_gates['both3']; f = old_gates['both3']
        if any(x['device'] not in mapped or mapped[x['device']]['terminals'][1] != x['gate_node'] for x in g+f):
            raise ValueError('Model flavor changed actual control-gate coverage')
        cells[profile] = c; banks[profile] = b; devices[profile] = ds; gates[profile] = f; tg_gates[profile] = g
        changes[profile] = dict(old_changes['both3'], **change,
                                both_driver_rc_models_have_actual_physical_witnesses=profile == 'tg_nlvt',
                                tg_component_physically_equivalent=False)
    paths += [evidence/'summary.json', *[ROOT/n for n in binding['inputs']]]
    paths += [parent/'manifest.json', *[parent/n for n in pm['libraries']]]
    return cells, banks, devices, gates, changes, paths, pdk_files, str(parent.relative_to(ROOT)), tg_gates


def fixture(out, spec, devices):
    text = source.fixture(out, dict(spec, profile='both3'), devices)
    title = 'OpenLVDS '+source.VERSION+'\n'; instance = ' '+source.circuit.name('both3')+'\n'
    if not text.startswith(title) or text.count(instance) != 1:
        raise ValueError('Matched NMOS flavor-isolation fixture changed')
    text = 'OpenLVDS '+VERSION+'\n'+text[len(title):].replace(instance, ' '+circuit.name(spec['profile'])+'\n', 1)
    for kind in ('cells', 'bank'):
        old = f'.include "{out}/{kind}_both3.spice"'
        if text.count(old) != 1:raise ValueError('Matched RC include changed')
        text = text.replace(old, f'.include "{out}/{kind}_{spec["profile"]}.spice"', 1)
    return text


def measure(folder, spec, devices, gates, tg_gates):
    result = source.measure(folder, spec, devices, gates, tg_gates)
    result.update(scope=SCOPE, inverter_rc_physically_equivalent=spec['profile'] == 'tg_nlvt',
                  tg_component_physically_equivalent=False, component_rc_physically_equivalent=False,
                  new_tg_junction_geometry='Original W/L and junction tokens retained; new NMOS-LVT implant layout not verified',
                  all_reference_rc_retained_for_flavor_isolation=True,
                  whole_bank_rc_retained=False, physical_parasitics_retained=False,
                  electrical_qualification_passed=False, qualified_phy=False)
    return result


def prepare(evidence):
    if helper.engine() != 'ngspice':
        raise ValueError('Require pinned native ngspice')
    cells, banks, devices, gates, changes, paths, pdk_files, baseline, tg_gates = libraries(evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    cad = changes[next(iter(circuit.PROFILES))]['component_provenance']['cad_python']
    tg_cad = changes[next(iter(circuit.PROFILES))]['tg_provenance']['cad_python']
    if tg_cad['path'] == cad['path'] and tg_cad['sha256'] != cad['sha256']:
        raise ValueError('CAD interpreter witnesses disagree')
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), parent=baseline,
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
    a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
