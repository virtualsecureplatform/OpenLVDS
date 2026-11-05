#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched uniform-bank diagnostic with idealized component interconnect only."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import probe_dcdl_uniform_tree_v3 as original
import uniform_tree_parasitic_isolation_v4 as isolation

ROOT = original.ROOT
VERSION = 'native-uniform-bank-parameter-preserving-parasitic-isolation-v4.1'
CONTEXT = 'dcdl_uniform_parasitic_v4'
SCOPE = ('Complete unchanged 16-tap/32-fine native bank, all MOS and native MIM parameters retained; '
         'explicit extracted R/C removed inside guarded buffer/fine components for diagnosis; '
         'source mux/control cells and ideal common wiring; no physical equivalence, code-update, '
         'dense-code, periodic-duty, all-PVT, electrical or PHY qualification')


def libraries(parent):
    m = original.bound(parent)
    original_cells = (parent/'cells.spice').read_text()
    bank = (parent/'bank.spice').read_text()
    definitions = original.circuit.native.definitions(original_cells)
    required = {original.circuit.BUFFER, original.circuit.fine.NAME}
    reports = []; texts = []
    for model in sorted(definitions):
        block = original.cell_definition(original_cells, model)
        if model in required:
            block, report = isolation.isolate(block, model)
            reports.append(report)
        texts.append(block.rstrip())
    if {r['model'] for r in reports} != required:
        raise ValueError('Missing original verified RC components')
    cells = '\n'.join(texts)+'\n'
    if {k: v[0] for k, v in original.circuit.native.definitions(cells).items()} != {k: v[0] for k, v in definitions.items()}:
        raise ValueError('Component interface/order changed')
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in original.circuit.ports()}
    devices = original.circuit.native.mapped_mos(cells+bank, original.circuit.name(), mapping, 'XD')
    old = m['identity']['devices']
    if (Counter((d['model'], d['limit_v']) for d in devices) != Counter((d['model'], d['limit_v']) for d in old)
            or len({d['name'] for d in devices}) != len(devices)):
        raise ValueError('Native MOS census or voltage coverage changed')
    return cells, bank, devices, reports


def fixture(out, spec, devices):
    text = original.fixture(out, spec, devices)
    title = 'OpenLVDS '+original.VERSION+'\n'
    if not text.startswith(title):
        raise ValueError('Matched native pulse fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def measure(folder, spec, devices):
    result = original.measure(folder, spec, devices)
    result['scope'] = SCOPE
    result['physical_parasitics_retained'] = False
    result['electrical_qualification_passed'] = False
    return result


def prepare(parent):
    if original.engine() != 'ngspice':
        raise ValueError('Use pinned native ngspice')
    pm = original.bound(parent)
    cells, bank, devices, reports = libraries(parent)
    inputs = [parent/n for n in ('manifest.json', 'cells.spice', 'bank.spice')]
    inputs += [ROOT/n for n in pm['identity']['inputs']]
    inputs += sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
                      if getattr(module, '__file__', None) and Path(module.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): original.sha(p) for p in inputs},
                    pdk_files=pm['identity']['pdk_files'], simulator=original.provenance(),
                    devices=devices, component_isolation=reports, specs=original.specifications(),
                    max_workers=2, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    original.write(out/'cells.spice', cells); original.write(out/'bank.spice', bank)
    tasks = []
    for n, spec in enumerate(identity['specs']):
        folder = out/str(n); folder.mkdir()
        original.write(folder/'bench.cir', fixture(out, spec, devices))
        tasks.append(dict(id=str(n), spec=spec, deck_sha256=original.sha(folder/'bench.cir')))
    original.atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
                    libraries={n: original.sha(out/n) for n in ('cells.spice', 'bank.spice')}, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != original.specifications() or i['max_workers'] != 2
            or original.engine() != 'ngspice' or original.provenance() != i['simulator']
            or any(original.sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(original.sha(Path(n)) != h for n, h in i['pdk_files'].items())
            or any(original.sha(out/n) != h for n, h in m['libraries'].items())
            or len(m['tasks']) != len(i['specs'])):
        raise ValueError('Native parasitic-isolation context changed')
    for n, task in enumerate(m['tasks']):
        if (task['id'] != str(n) or task['spec'] != i['specs'][n]
                or original.sha(out/str(n)/'bench.cir') != task['deck_sha256']
                or (out/str(n)/'bench.cir').read_text() != fixture(out, task['spec'], i['devices'])):
            raise ValueError('Matched native parasitic-isolation task changed')
    return m


def run(out):
    m = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior parasitic-isolation campaign')
        original.atomic(out/'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out/task['id']; result = error = wall = None
            try:
                with original.lease(ROOT, priority=0, label=CONTEXT+'_'+task['id']):
                    bound(out); start = time.monotonic()
                    p = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'), '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                    wall = time.monotonic()-start
                original.write(folder/'console.log', p.stdout+p.stderr)
                p.check_returncode(); result = measure(folder, task['spec'], m['identity']['devices'])
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
