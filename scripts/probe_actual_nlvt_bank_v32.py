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
import actual_nlvt_bank_v31 as circuit
import probe_nlvt_data_path_v25 as original
import verify_nlvt_data_path_v25 as original_proof
import probe_tg_component_bank_v23 as source
import verify_tg_component_bank_v23 as baseline_proof
import recover_tg_component_rc_v8 as recovery
import measure_tg_component_rc_v8 as measurement

previous = recovery.producer
helper = previous.previous.previous.original
ROOT = previous.ROOT
VERSION = 'actual-stacked-tg-and-low-vt-data-component-rc-zero-screen-v32.1'
CONTEXT = 'actual_nlvt_bank_v32'
SCOPE = ('Complete 903-MOS 16-tap/32-fine bank with independently verified actual stacked NMOS-LVT TG, '
         'NMOS-LVT data-driver and coarse-buffer component RC; all 93 fine and 40 actual TG gates observed; '
         'zero-code SS/40 C only; SC control/common/tail-cap wiring remains unextracted; '
         'no full sparse/dense/update/periodic-duty/all-PVT, whole-bank or PHY qualification')


def specifications():
    return [dict(source.specifications()[1], profile='actual_nlvt')]


def libraries(evidence, tg_evidence, data_evidence):
    receipt = json.loads((evidence/'summary.json').read_text()); binding = receipt['identity']
    baseline = ROOT/binding['parent']
    if (evidence.parent != ROOT/'build/diagnostics'/original_proof.CONTEXT
            or not receipt['all_declared_cases_consumed'] or receipt['qualified_phy']
            or original_proof.verify(baseline) != evidence):
        raise ValueError('Require complete verified low-Vt data timing-only failure')
    pm = original.bound(baseline); pi = pm['identity']; profile = 'actual_nlvt'
    original_result = next(r['result'] for r in receipt['rows'] if r['task']['spec']['profile'] == 'data_nlvt')
    if (original_result['zero_code_fast_quarter_headroom_ps'] >= 0
            or not original_result['terminal_screen_passed'] or not original_result['control_settling_passed']):
        raise ValueError('Require the preserved low-Vt timing-only failure')
    components, paths, external, provenance = circuit.witnesses(tg_evidence, data_evidence)
    c, b, change = circuit.transform((baseline/'cells_data_nlvt.spice').read_text(),
                                      (baseline/'bank_data_nlvt.spice').read_text(), components)
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in source.circuit.controls.dimensions.ports()}
    ds = helper.circuit.native.mapped_mos(c+b, circuit.name(profile), mapping, 'XD')
    if (len(ds) != 903 or len({d['name'] for d in ds}) != 903
            or Counter((d['model'],d['limit_v']) for d in ds) != Counter((d['model'],d['limit_v']) for d in pi['devices']['data_nlvt'])):
        raise ValueError('Actual component RC changed native model counts or voltage limits')
    g = circuit.gate_observations(components['tg'], b); f = pi['fine_control_gates']['data_nlvt']
    mapped = {d['name']:d for d in ds}
    if len(g) != 40 or len(f) != 93 or any(x['device'] not in mapped or mapped[x['device']]['terminals'][1] != x['gate_node'] for x in g+f):
        raise ValueError('Actual low-Vt component control-gate coverage changed')
    paths += [evidence/'summary.json', *[ROOT/n for n in binding['inputs']]]
    paths += [baseline/'manifest.json', *[baseline/n for n in pm['libraries']]]
    paths += [ROOT/n for n in pi['inputs']]
    change.update(component_provenance=provenance, tg_provenance=provenance)
    return ({profile:c}, {profile:b}, {profile:ds}, {profile:f}, {profile:change}, paths,
            circuit.merge_files(pi['pdk_files'], pi['external_files'], external), str(baseline.relative_to(ROOT)), {profile:g})


def fixture(out, spec, devices):
    text = original.fixture(out, dict(spec, profile='data_nlvt'), devices)
    title = 'OpenLVDS '+original.VERSION+'\n'; instance = ' '+original.circuit.name('data_nlvt')+'\n'
    if not text.startswith(title) or text.count(instance) != 1:
        raise ValueError('Matched actual low-Vt component fixture changed')
    text = 'OpenLVDS '+VERSION+'\n'+text[len(title):].replace(instance, ' '+circuit.name(spec['profile'])+'\n', 1)
    for kind in ('cells', 'bank'):
        old = f'.include "{out}/{kind}_data_nlvt.spice"'
        if text.count(old) != 1: raise ValueError('Matched component include changed')
        text = text.replace(old, f'.include "{out}/{kind}_{spec["profile"]}.spice"', 1)
    return text


def measure(folder, spec, devices, gates, tg_gates):
    result = source.measure(folder, spec, devices, gates, tg_gates)
    result.update(scope=SCOPE, inverter_rc_physically_equivalent=True,
                  tg_component_physically_equivalent=True, component_rc_physically_equivalent=True,
                  borrowed_changed_implant_rc=False,
                  new_tg_junction_geometry='Actual independently verified stacked NMOS-LVT/P-regular GDS and component RC',
                  whole_bank_rc_retained=False, physical_parasitics_retained=False,
                  electrical_qualification_passed=False, qualified_phy=False)
    return result


def prepare(evidence, tg_evidence, data_evidence):
    if helper.engine() != 'ngspice':
        raise ValueError('Require pinned native ngspice')
    cells, banks, devices, gates, changes, paths, pdk_files, baseline, tg_gates = libraries(evidence, tg_evidence, data_evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    cad = changes[next(iter(circuit.PROFILES))]['component_provenance']['cad_python']
    tg_cad = changes[next(iter(circuit.PROFILES))]['tg_provenance']['cad_python']
    if tg_cad['path'] == cad['path'] and tg_cad['sha256'] != cad['sha256']:
        raise ValueError('CAD interpreter witnesses disagree')
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), tg_evidence=str(tg_evidence.relative_to(ROOT)), data_evidence=str(data_evidence.relative_to(ROOT)), parent=baseline,
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
    p.add_argument('--tg-evidence', type=Path); p.add_argument('--data-evidence', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        if a.tg_evidence is None or a.data_evidence is None: p.error('Both component proofs are required')
        print(prepare(a.artifact.resolve(), a.tg_evidence.resolve(), a.data_evidence.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
