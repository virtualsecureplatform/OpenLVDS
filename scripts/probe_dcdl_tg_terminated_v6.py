#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched native screen of a real MIM termination on the balancing output."""
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
import dcdl_tg_terminated_v6 as circuit
import probe_dcdl_tg_tree_v5 as previous
import verify_dcdl_tg_tree_v5 as proof
from native_binary_raw_v2 import validate

ROOT = previous.ROOT
VERSION = 'native-tg-bank-single-mim-tail-termination-screen-v6.1'
CONTEXT = 'dcdl_tg_terminated_v6'
SCOPE = ('Full 16-tap/32-fine double-TG direct bank with one native 2x2 MIM added to the balancing output; '
         'all 903 MOS devices/parameters and original control/data wiring retained; component wiring '
         'idealized and TG junctions remain prelayout estimates; no new physical geometry/RC, code-update, '
         'dense-code, periodic-duty, all-PVT, electrical or PHY qualification')


def specifications():
    return [s for s in previous.specifications() if s['profile'] == circuit.PROFILE]


def libraries(evidence):
    report = json.loads((evidence/'summary.json').read_text()); i = report['identity']
    if (evidence.parent != ROOT/'build/diagnostics'/proof.CONTEXT or i['version'] != proof.VERSION
            or evidence.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or not report['all_consumed_complete_native_waveforms_verified'] or report['qualified_phy']
            or any(previous.original.sha(ROOT/n) != h for n, h in i['inputs'].items())):
        raise ValueError('Require unchanged independently verified native TG cases')
    parent = ROOT/i['parent']; pm = previous.bound(parent)
    rows = [r for r in report['rows'] if r['task']['spec']['profile'] == circuit.PROFILE
            and r['task']['spec']['coarse'] == r['task']['spec']['fine'] == 0]
    if len(rows) != 1:
        raise ValueError('Require the unique matched direct zero-code case')
    row = rows[0]; result = row['result']; task = row['task']; folder = parent/task['id']
    retained = json.loads((folder/'summary.json').read_text())
    if (retained['task'] != task or retained['error'] is not None or retained['result'] != result
            or previous.measure(folder, task['spec'], pm['identity']['devices'][circuit.PROFILE]) != result
            or result['zero_code_fast_quarter_headroom_ps'] <= 0
            or not result['control_settling_passed'] or not result['onehot_control_settling_passed']):
        raise ValueError('Require the complete timing/control-passing direct zero-code baseline')
    violations = [d for d in result['terminal_stress'] if not d['passed']]
    if not violations or any(not d['device'].startswith('XD:Xtail_load:') for d in violations):
        raise ValueError('Require the measured balancing-buffer-only voltage failure')
    cells = (parent/'cells.spice').read_text()
    orders = {m: d[0] for m, d in previous.original.circuit.native.definitions(cells).items()}
    original_bank = previous.original.cell_definition((parent/'banks.spice').read_text(), circuit.previous.name(circuit.PROFILE))
    if original_bank != circuit.previous.source(orders, circuit.PROFILE):
        raise ValueError('Retained native data/control graph changed')
    bank = circuit.source(orders)
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in circuit.previous.dimensions.ports()}
    devices = previous.original.circuit.native.mapped_mos(cells+bank, circuit.name(), mapping, 'XD')
    if devices != pm['identity']['devices'][circuit.PROFILE]:
        raise ValueError('Tail termination changed any active MOS or terminal connection')
    paths = [evidence/'summary.json', *[ROOT/n for n in i['inputs']]]
    paths += [parent/n for n in ('manifest.json', 'cells.spice', 'banks.spice')]
    paths += [ROOT/n for n in pm['identity']['inputs']]
    return cells, bank, devices, paths, pm['identity']['pdk_files'], str(parent.relative_to(ROOT))


def fixture(out, spec, devices):
    text = previous.fixture(out, spec, devices)
    title = 'OpenLVDS '+previous.VERSION+'\n'
    instance = ' '+circuit.previous.name(circuit.PROFILE)+'\n'
    include = f'.include "{out}/banks.spice"'
    if not text.startswith(title) or text.count(instance) != 1 or text.count(include) != 1:
        raise ValueError('Matched native TG fixture changed')
    text = 'OpenLVDS '+VERSION+'\n'+text[len(title):]
    return text.replace(instance, ' '+circuit.name()+'\n', 1).replace(include, f'.include "{out}/bank.spice"', 1)


def measure(folder, spec, devices):
    result = previous.measure(folder, spec, devices)
    names, w = validate(folder/'bench.raw', {'v(xd.unused_tail)'}, 20e-9)
    values = w[:, names.index('v(xd.unused_tail)')]
    result.update(tail_output_minimum_v=float(np.min(values)), tail_output_maximum_v=float(np.max(values)),
                  tail_termination_um=[circuit.WIDTH, circuit.LENGTH], scope=SCOPE,
                  electrical_qualification_passed=False, qualified_phy=False)
    return result


def prepare(evidence):
    if previous.original.engine() != 'ngspice':
        raise ValueError('Use pinned native ngspice')
    cells, bank, devices, paths, pdk_files, parent = libraries(evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), parent=parent,
                    inputs={str(p.relative_to(ROOT)): previous.original.sha(p) for p in paths}, pdk_files=pdk_files,
                    simulator=previous.original.provenance(), devices=devices, specs=specifications(),
                    tail_termination_um=[2, 2], max_workers=2, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    previous.original.write(out/'cells.spice', cells); previous.original.write(out/'bank.spice', bank)
    tasks = []
    for n, spec in enumerate(identity['specs']):
        folder = out/str(n); folder.mkdir()
        previous.original.write(folder/'bench.cir', fixture(out, spec, devices))
        tasks.append(dict(id=str(n), spec=spec, deck_sha256=previous.original.sha(folder/'bench.cir')))
    previous.original.atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
        libraries={n: previous.original.sha(out/n) for n in ('cells.spice', 'bank.spice')}, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['max_workers'] != 2 or i['tail_termination_um'] != [2, 2]
            or previous.original.engine() != 'ngspice' or previous.original.provenance() != i['simulator']
            or any(previous.original.sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(previous.original.sha(Path(n)) != h for n, h in i['pdk_files'].items())
            or any(previous.original.sha(out/n) != h for n, h in m['libraries'].items())
            or len(m['tasks']) != len(i['specs'])):
        raise ValueError('Native terminated-bank context changed')
    for n, task in enumerate(m['tasks']):
        if (task['id'] != str(n) or task['spec'] != i['specs'][n]
                or previous.original.sha(out/str(n)/'bench.cir') != task['deck_sha256']
                or (out/str(n)/'bench.cir').read_text() != fixture(out, task['spec'], i['devices'])):
            raise ValueError('Native terminated-bank task changed')
    return m


def run(out):
    m = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior native termination campaign')
        previous.original.atomic(out/'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out/task['id']; result = error = wall = None
            try:
                with previous.original.lease(ROOT, priority=0, label=CONTEXT+'_'+task['id']):
                    bound(out); start = time.monotonic()
                    p = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'), '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                    wall = time.monotonic()-start
                previous.original.write(folder/'console.log', p.stdout+p.stderr); p.check_returncode()
                result = measure(folder, task['spec'], m['identity']['devices'])
            except Exception as e:
                error = str(e)
            row = dict(task=task, result=result, error=error, solver_wall_seconds=wall,
                       files={p.name: previous.original.sha(p) for p in folder.iterdir() if p.is_file()})
            previous.original.atomic(folder/'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, m['tasks']))
        bound(out)
        previous.original.atomic(out/'summary.json', dict(rows=rows, qualified_phy=False, scope=SCOPE))
        previous.original.atomic(out/'state.json', dict(status='complete', cases=len(rows), errors=sum(r['error'] is not None for r in rows), qualified_phy=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
