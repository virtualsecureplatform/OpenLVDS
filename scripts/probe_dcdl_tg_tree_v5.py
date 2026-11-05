#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete native TG-bank architecture screen, with all physical gates closed."""
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
import dcdl_tg_tree_v5 as circuit
import diagnose_uniform_zero_v4 as diagnosis
import probe_dcdl_uniform_tree_v3 as original
import uniform_tree_parasitic_isolation_v4 as isolation
from native_binary_raw_v2 import validate

ROOT = original.ROOT
VERSION = 'native-static-onehot-tg-tree-separate-fine-driver-screen-v5.1'
CONTEXT = 'dcdl_tg_tree_v5'
SCOPE = ('Complete 16-tap/32-fine native source architecture screen; original extracted MOS/MIM '
         'parameters retained in idealized buffer/inverter/fine components; new TGs have explicit '
         'prelayout junction estimates, native SC source controls and ideal common wiring; no physical '
         'RC, code-update, dense-code, periodic-duty, all-PVT, electrical or PHY qualification')


def specifications():
    return [dict(profile=profile, process='ss', temperature=40, coarse=c, fine=f,
                 input_slew_ps=100, load_ff=20)
            for c, f in ((0, 0), (0, 1), (0, 15), (0, 16), (0, 31), (1, 0))
            for profile in circuit.PROFILES]


def libraries(evidence):
    receipt = json.loads((evidence/'summary.json').read_text())
    source_parent = ROOT/receipt['identity']['source_parent']
    if diagnosis.diagnose(source_parent) != evidence:
        raise ValueError('Require the exact complete failed mux4-bank native checkpoint')
    if (receipt['physical_component_rc']['zero_code_fast_quarter_headroom_ps'] >= 0
            or receipt['idealized_component_wiring']['zero_code_fast_quarter_headroom_ps'] >= 0):
        raise ValueError('Require measured native architecture failure before replacement')
    parent = ROOT/receipt['identity']['rc_parent']; pm = original.bound(parent)
    compound, paths = original.components.families.witnesses(ROOT/pm['identity']['compound'])
    clock, clock_paths = original.components.families.witnesses(ROOT/pm['identity']['clock'])
    paths += clock_paths
    fine = original.cell_definition((parent/'cells.spice').read_text(), circuit.FINE)
    texts = []; reports = []
    for model, text in ((circuit.BUFFER, compound[circuit.BUFFER]['text']),
                        (circuit.INVERTER, clock[circuit.INVERTER]['text']), (circuit.FINE, fine)):
        source, report = isolation.isolate(text, model)
        texts.append(source.rstrip()); reports.append(report)
    sc = next(Path(n) for n in pm['identity']['pdk_files'] if n.endswith('/sky130_fd_sc_hd.spice'))
    library = sc.read_text()
    for short in ('buf_1', 'inv_1', 'buf_4', 'inv_4', 'and2_4'):
        texts.append(original.cell_definition(library, circuit.SC+short).rstrip())
    texts += [circuit.tg_source(profile).rstrip() for profile in circuit.PROFILES]
    cells = '\n'.join(texts)+'\n'
    orders = {m: d[0] for m, d in original.circuit.native.definitions(cells).items()}
    banks = {}; devices = {}
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in circuit.dimensions.ports()}
    for profile in circuit.PROFILES:
        bank = circuit.source(orders, profile); banks[profile] = bank
        mos = original.circuit.native.mapped_mos(cells+bank, circuit.name(profile), mapping, 'XD')
        if not mos or any(d['limit_v'] != 1.95 for d in mos) or len({d['name'] for d in mos}) != len(mos):
            raise ValueError('Native TG-bank MOS terminal coverage failed')
        devices[profile] = mos
    paths += [evidence/'summary.json']
    paths += [ROOT/n for n in receipt['identity']['inputs']]
    paths += [parent/n for n in ('manifest.json', 'cells.spice', 'bank.spice')]
    paths += [ROOT/n for n in pm['identity']['inputs']]
    return cells, banks, devices, reports, paths, pm['identity']['pdk_files']


def fixture(out, spec, devices):
    text = original.fixture(out, spec, devices)
    title = 'OpenLVDS '+original.VERSION+'\n'
    include = f'.include "{out}/bank.spice"'
    instance = ' '+original.circuit.name()+'\n'
    if not text.startswith(title) or text.count(include) != 1 or text.count(instance) != 1:
        raise ValueError('Original matched native pulse source/interface changed')
    text = 'OpenLVDS '+VERSION+'\n'+text[len(title):]
    text = text.replace(include, f'.include "{out}/banks.spice"', 1)
    text = text.replace(instance, ' '+circuit.name(spec['profile'])+'\n', 1)
    return text


def measure(folder, spec, devices):
    result = original.measure(folder, spec, devices)
    targets = circuit.control_targets(spec['coarse'], spec['fine'])
    requested = {'v(xd.'+node.lower()+')' for node in targets}
    names, w = validate(folder/'bench.raw', requested, 20e-9)
    idx = {n: i for i, n in enumerate(names)}; stable = w[:, idx['time']] >= 1.5e-9
    controls = []
    for node, target in targets.items():
        deviation = float(np.max(np.abs(w[stable, idx['v(xd.'+node.lower()+')']]-1.8*target)))
        controls.append(dict(node=node, deviation_v=deviation, passed=bool(deviation <= .18)))
    result.update(onehot_controls=controls, onehot_control_settling_passed=all(c['passed'] for c in controls),
                  electrical_qualification_passed=False, physical_parasitics_retained=False,
                  new_tg_junction_geometry='Explicit prelayout estimates; no new TG GDS/PCell/extraction proof', scope=SCOPE)
    return result


def prepare(evidence):
    if original.engine() != 'ngspice':
        raise ValueError('Use pinned native ngspice')
    cells, banks, devices, reports, paths, pdk_files = libraries(evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): original.sha(p) for p in paths},
                    pdk_files=pdk_files, simulator=original.provenance(), component_isolation=reports,
                    devices=devices, specs=specifications(), max_workers=2, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    original.write(out/'cells.spice', cells)
    original.write(out/'banks.spice', '\n'.join(banks.values()))
    tasks = []
    for n, spec in enumerate(identity['specs']):
        folder = out/str(n); folder.mkdir()
        original.write(folder/'bench.cir', fixture(out, spec, devices[spec['profile']]))
        tasks.append(dict(id=str(n), spec=spec, deck_sha256=original.sha(folder/'bench.cir')))
    original.atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
                    libraries={n: original.sha(out/n) for n in ('cells.spice', 'banks.spice')}, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['max_workers'] != 2
            or original.engine() != 'ngspice' or original.provenance() != i['simulator']
            or any(original.sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(original.sha(Path(n)) != h for n, h in i['pdk_files'].items())
            or any(original.sha(out/n) != h for n, h in m['libraries'].items())
            or len(m['tasks']) != len(i['specs'])):
        raise ValueError('Native TG-bank context changed')
    for n, task in enumerate(m['tasks']):
        if (task['id'] != str(n) or task['spec'] != i['specs'][n]
                or original.sha(out/str(n)/'bench.cir') != task['deck_sha256']
                or (out/str(n)/'bench.cir').read_text() != fixture(out, task['spec'], i['devices'][task['spec']['profile']])):
            raise ValueError('Native TG-bank pulse task changed')
    return m


def run(out):
    m = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior native TG campaign')
        original.atomic(out/'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out/task['id']; result = error = wall = None
            try:
                with original.lease(ROOT, priority=0, label=CONTEXT+'_'+task['id']):
                    bound(out); start = time.monotonic()
                    p = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'), '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                    wall = time.monotonic()-start
                original.write(folder/'console.log', p.stdout+p.stderr); p.check_returncode()
                result = measure(folder, task['spec'], m['identity']['devices'][task['spec']['profile']])
            except Exception as e:
                error = str(e)
            row = dict(task=task, result=result, error=error, solver_wall_seconds=wall,
                       files={p.name: original.sha(p) for p in folder.iterdir() if p.is_file()})
            original.atomic(folder/'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, m['tasks']))
        bound(out)
        original.atomic(out/'summary.json', dict(rows=rows, qualified_phy=False, scope=SCOPE))
        original.atomic(out/'state.json', dict(status='complete', cases=len(rows), errors=sum(r['error'] is not None for r in rows), qualified_phy=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
