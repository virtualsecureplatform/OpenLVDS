#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test wider TGs for routed-clock headroom while preserving the full fine range."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import tg_headroom_experiment_v12 as circuit
import recover_tg_component_rc_v8 as recovery
import measure_tg_component_rc_v8 as measurement

previous = recovery.producer
helper = previous.previous.previous.original
ROOT = previous.ROOT
VERSION = 'native-regular-pmos-oct-tg-headroom-borrowed-rc-screen-v12.1'
CONTEXT = 'tg_headroom_experiment_v12'
SCOPE = ('Complete native terminated 16-tap/32-fine bank; test N3.36/P6.72 TGs and regular-Vt input/fine-driver PMOS for more quarter-period headroom; '
         'all buffer/fine-unit component RC retained, inverter wiring RC borrowed from HVT layout for flavor isolation; '
         'TG junctions estimated, controls/common/tail-cap routing unextracted; no new inverter physical equivalence, '
         'whole-bank RC, dense-code, code-update, periodic-duty, all-PVT, electrical or PHY qualification')


def specifications():
    return [dict(spec, profile=profile) for spec in previous.specifications() for profile in circuit.PROFILES]


def libraries(evidence):
    report = json.loads((evidence/'summary.json').read_text()); binding = report['identity']
    parent = ROOT/binding['parent']
    if (evidence.parent != ROOT/'build/diagnostics'/recovery.CONTEXT
            or recovery.verify(parent) != evidence or not report['all_declared_cases_consumed']
            or report['profile']['sparse_native_screen_passed'] or report['qualified_phy']):
        raise ValueError('Require the complete independently recovered component-RC timing failure')
    pm = previous.bound(parent); baseline = pm['identity']
    cells = {}; banks = {}; devices = {}; changes = {}; gates = {}
    source_cells = (parent/'cells.spice').read_text(); source_bank = (parent/'bank.spice').read_text()
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in circuit.baseline.previous.dimensions.ports()}
    for profile in circuit.PROFILES:
        c, b, change = circuit.transform(source_cells, source_bank, profile)
        ds = helper.circuit.native.mapped_mos(c+b, circuit.name(profile), mapping, 'XD')
        if (len(ds) != 903 or len({d['name'] for d in ds}) != 903
                or [(d['name'], d['terminals'], d['limit_v']) for d in ds]
                != [(d['name'], d['terminals'], d['limit_v']) for d in baseline['devices']]):
            raise ValueError('Driver experiment changed the complete active-terminal census')
        g = previous.components.fine_gate_observations(helper.cell_definition(c, circuit.baseline.previous.FINE), b)
        if g != baseline['fine_control_gates']:
            raise ValueError('Driver experiment changed distributed fine-gate coverage')
        cells[profile] = c; banks[profile] = b; devices[profile] = ds; changes[profile] = change; gates[profile] = g
    paths = [evidence/'summary.json', *[ROOT/n for n in binding['inputs']]]
    paths += [parent/n for n in ('manifest.json', 'cells.spice', 'bank.spice')]
    return cells, banks, devices, gates, changes, paths, baseline['pdk_files'], str(parent.relative_to(ROOT))


def fixture(out, spec, devices):
    # Reuse the same 20 ns, two-pulse source and every active terminal probe.
    text = previous.fixture(out, dict(spec, profile=circuit.baseline.PROFILE), devices)
    title = 'OpenLVDS '+previous.VERSION+'\n'
    instance = ' '+circuit.baseline.name()+'\n'
    if not text.startswith(title) or text.count(instance) != 1:
        raise ValueError('Matched native pulse fixture changed')
    text = 'OpenLVDS '+VERSION+'\n'+text[len(title):]
    for kind in ('cells', 'bank'):
        old = f'.include "{out}/{kind}.spice"'
        if text.count(old) != 1:
            raise ValueError('Matched native component include changed')
        text = text.replace(old, f'.include "{out}/{kind}_{spec["profile"]}.spice"', 1)
    return measurement.add_public_probes(text.replace(instance, ' '+circuit.name(spec['profile'])+'\n', 1))


def measure(folder, spec, devices, gates):
    result = measurement.measure(folder, spec, devices, gates)
    if not result['public_tail_range_available']:
        raise ValueError('New driver experiment omitted its passive public tail probe')
    result.update(scope=SCOPE, component_parasitics_retained=True, inverter_rc_physically_equivalent=False,
                  whole_bank_rc_retained=False, physical_parasitics_retained=False,
                  electrical_qualification_passed=False, qualified_phy=False)
    return result


def prepare(evidence):
    if helper.engine() != 'ngspice':
        raise ValueError('Require pinned native ngspice')
    cells, banks, devices, gates, changes, paths, pdk_files, parent = libraries(evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), parent=parent,
                    inputs={str(p.relative_to(ROOT)): helper.sha(p) for p in paths}, pdk_files=pdk_files,
                    simulator=helper.provenance(), devices=devices, fine_control_gates=gates, changes=changes,
                    specs=specifications(), max_workers=1, scope=SCOPE)
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
            or i['specs'] != specifications() or i['max_workers'] != 1
            or set(m['libraries']) != {f'{kind}_{profile}.spice' for kind in ('cells', 'bank') for profile in circuit.PROFILES}
            or helper.engine() != 'ngspice' or helper.provenance() != i['simulator']
            or any(helper.sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(helper.sha(Path(n)) != h for n, h in i['pdk_files'].items())
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
                result = measure(folder, task['spec'], m['identity']['devices'][profile], m['identity']['fine_control_gates'][profile])
            except Exception as e:
                error = str(e)
            row = dict(task=task, result=result, error=error, solver_wall_seconds=wall,
                       files={p.name: helper.sha(p) for p in folder.iterdir() if p.is_file()})
            helper.atomic(folder/'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=1) as pool:
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
