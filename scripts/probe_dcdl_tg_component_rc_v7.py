#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Restore verified native component RC around the passing terminated TG bank."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import probe_dcdl_tg_terminated_v6 as previous
import verify_dcdl_tg_terminated_v6 as proof
import tg_component_rc_families_v7 as components
from native_binary_raw_v2 import validate

ROOT = previous.ROOT
VERSION = 'native-terminated-tg-bank-verified-component-rc-screen-v7.1'
CONTEXT = 'dcdl_tg_component_rc_v7'
SCOPE = ('Complete terminated 16-tap/32-fine native TG bank with exact verified buffer/inverter/fine '
         'component RC restored; all native primitive parameters retained, distributed fine gates '
         'observed; new TG junctions remain estimated and TG/control/common/tail-cap routing is '
         'unextracted; no whole-bank RC, dense-code, code-update, periodic-duty, all-PVT or PHY qualification')


def specifications():
    return previous.specifications()


def libraries(evidence):
    report = json.loads((evidence/'summary.json').read_text()); binding = report['identity']
    parent = ROOT/binding['parent']
    if (evidence.parent != ROOT/'build/diagnostics'/proof.CONTEXT or binding['version'] != proof.VERSION
            or evidence.name != hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
            or not report['all_declared_cases_consumed'] or not report['all_consumed_complete_native_waveforms_verified']
            or not report['profile']['sparse_native_screen_passed'] or report['qualified_phy']
            or proof.verify(parent) != evidence):
        raise ValueError('Require the independently rechecked complete passing sparse TG checkpoint')
    pm = previous.bound(parent)
    vm = previous.previous.bound(ROOT/pm['identity']['parent'])
    failed = json.loads((ROOT/vm['identity']['evidence']/'summary.json').read_text())
    rc_parent = ROOT/failed['identity']['rc_parent']
    original = previous.previous.original; rm = original.bound(rc_parent)
    ri = rm['identity']
    sc = next(Path(n) for n in ri['pdk_files'] if n.endswith('/sky130_fd_sc_hd.spice'))
    regenerated, _, _, regenerated_paths = original.libraries(ROOT/ri['compound'], ROOT/ri['fine'], ROOT/ri['clock'], sc)
    if regenerated != (rc_parent/'cells.spice').read_text():
        raise ValueError('Original verified fine/component RC witness changed')
    compound, paths = original.components.families.witnesses(ROOT/ri['compound'])
    clock, clock_paths = original.components.families.witnesses(ROOT/ri['clock'])
    paths += clock_paths+regenerated_paths
    models = {
        components.circuit.previous.BUFFER: compound[components.circuit.previous.BUFFER]['text'],
        components.circuit.previous.INVERTER: clock[components.circuit.previous.INVERTER]['text'],
        components.circuit.previous.FINE: original.cell_definition(regenerated, components.circuit.previous.FINE),
    }
    cells, restored = components.restore((parent/'cells.spice').read_text(), models)
    bank = (parent/'bank.spice').read_text()
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in previous.circuit.previous.dimensions.ports()}
    devices = original.circuit.native.mapped_mos(cells+bank, previous.circuit.name(), mapping, 'XD')
    def census(ds):
        return [(d['name'], d['model'], d['limit_v']) for d in ds]
    if census(devices) != census(pm['identity']['devices']):
        raise ValueError('Component RC restoration changed the native device census')
    gates = components.fine_gate_observations(models[components.circuit.previous.FINE], bank)
    mapped = {d['name']: d for d in devices}
    if len(gates) != 93 or any(g['device'] not in mapped or mapped[g['device']]['terminals'][1] != g['gate_node'] for g in gates):
        raise ValueError('Distributed native fine control-gate coverage failed')
    paths += [evidence/'summary.json', *[ROOT/n for n in binding['inputs']]]
    paths += [parent/n for n in ('manifest.json', 'cells.spice', 'bank.spice')]
    paths += [ROOT/n for n in pm['identity']['inputs']]
    paths += [rc_parent/n for n in ('manifest.json', 'cells.spice')]
    return cells, bank, devices, gates, restored, paths, pm['identity']['pdk_files'], str(parent.relative_to(ROOT))


def fixture(out, spec, devices):
    text = previous.fixture(out, spec, devices)
    title = 'OpenLVDS '+previous.VERSION+'\n'
    if not text.startswith(title):
        raise ValueError('Matched native termination fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def measure(folder, spec, devices, gates):
    result = previous.measure(folder, spec, devices)
    def column(n):
        return 'v('+n.replace(':', '.').lower()+')'
    names, w = validate(folder/'bench.raw', {column(g['gate_node']) for g in gates}, 20e-9)
    idx = {n: i for i, n in enumerate(names)}; stable = w[:, idx['time']] >= 1.5e-9
    controls = []
    for gate in gates:
        enabled = int(gate['bit'] < spec['fine'])
        target = 1.8*(enabled if gate['kind'] == 'fine' else 1-enabled)
        deviation = float(np.max(np.abs(w[stable, idx[column(gate['gate_node'])]]-target)))
        controls.append(dict(gate, maximum_deviation_v=deviation, passed=bool(deviation <= .18)))
    public = result['control_settling_passed']
    internal = all(c['passed'] for c in controls)
    result.update(public_control_settling_passed=public, distributed_fine_controls=controls,
                  distributed_control_settling_passed=internal, control_settling_passed=bool(public and internal),
                  component_parasitics_retained=True, physical_parasitics_retained=False,
                  whole_bank_rc_retained=False, scope=SCOPE, electrical_qualification_passed=False, qualified_phy=False)
    return result


def prepare(evidence):
    if previous.previous.original.engine() != 'ngspice':
        raise ValueError('Use pinned native ngspice')
    cells, bank, devices, gates, restored, paths, pdk_files, parent = libraries(evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), parent=parent,
                    inputs={str(p.relative_to(ROOT)): previous.previous.original.sha(p) for p in paths},
                    pdk_files=pdk_files, simulator=previous.previous.original.provenance(), devices=devices,
                    fine_control_gates=gates, restored_components=restored, specs=specifications(), max_workers=2, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    previous.previous.original.write(out/'cells.spice', cells); previous.previous.original.write(out/'bank.spice', bank)
    tasks = []
    for n, spec in enumerate(identity['specs']):
        folder = out/str(n); folder.mkdir()
        previous.previous.original.write(folder/'bench.cir', fixture(out, spec, devices))
        tasks.append(dict(id=str(n), spec=spec, deck_sha256=previous.previous.original.sha(folder/'bench.cir')))
    previous.previous.original.atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
        libraries={n: previous.previous.original.sha(out/n) for n in ('cells.spice', 'bank.spice')}, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']; helper = previous.previous.original
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['max_workers'] != 2 or len(i['fine_control_gates']) != 93
            or helper.engine() != 'ngspice' or helper.provenance() != i['simulator']
            or any(helper.sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(helper.sha(Path(n)) != h for n, h in i['pdk_files'].items())
            or any(helper.sha(out/n) != h for n, h in m['libraries'].items()) or len(m['tasks']) != len(i['specs'])):
        raise ValueError('Native component-RC context changed')
    for n, task in enumerate(m['tasks']):
        if (task['id'] != str(n) or task['spec'] != i['specs'][n]
                or helper.sha(out/str(n)/'bench.cir') != task['deck_sha256']
                or (out/str(n)/'bench.cir').read_text() != fixture(out, task['spec'], i['devices'])):
            raise ValueError('Native component-RC task changed')
    return m


def run(out):
    m = bound(out); helper = previous.previous.original
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior component-RC campaign')
        helper.atomic(out/'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out/task['id']; result = error = wall = None
            try:
                with helper.lease(ROOT, priority=0, label=CONTEXT+'_'+task['id']):
                    bound(out); start = time.monotonic()
                    p = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'), '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                    wall = time.monotonic()-start
                helper.write(folder/'console.log', p.stdout+p.stderr); p.check_returncode()
                result = measure(folder, task['spec'], m['identity']['devices'], m['identity']['fine_control_gates'])
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
