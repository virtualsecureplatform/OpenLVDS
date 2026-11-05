#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native static-code pilot of the complete uniform-tap/thermometer bank.

Retain component RC for buffers and fine units; native source mux/control
cells and ideal common wires are explicitly unqualified. No PHY admission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import dcdl_uniform_tree_v3 as circuit
import probe_dcdl_mux_return_v2 as components
from build_compound_drivers_v3 import cell_definition
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha, write, atomic, crossings
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'native-uniform-tap-balanced-tree-static-code-pilot-v3.1'
CONTEXT = 'dcdl_uniform_tree_v3'
SCOPE = ('Complete 16-tap/32-fine native bank, two isolated static-code pulses; '
         'component buffer/fine RC, source mux/control cells, ideal common wires; '
         'no code-update, dense-code, periodic-duty, whole-bank RC, all-PVT or PHY qualification')


def specifications():
    return [dict(process='ss', temperature=40, coarse=c, fine=f,
                 input_slew_ps=100, load_ff=20)
            for c in (0, 1) for f in (0, 1, 15, 16, 31)]


def libraries(compound, fine, clock, sc):
    old_cells, _, orders, _, paths = components.libraries(compound, fine, sc)
    clock_cells, clock_paths = components.families.witnesses(clock)
    if circuit.BUFFER not in clock_cells:
        raise ValueError('Missing verified clock-buffer RC')
    old_cells += clock_cells[circuit.BUFFER]['text']
    paths += clock_paths
    definitions = circuit.native.definitions(old_cells)
    texts = []
    required = sorted({c['model'] for c in circuit.instances()})
    for model in required:
        block = cell_definition(old_cells if model in definitions else sc.read_text(), model)
        texts.append(block.rstrip())
        orders[model] = circuit.native.definitions(block)[model][0]
    cells = '\n'.join(texts)+'\n'
    bank = circuit.source(orders)
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in circuit.ports()}
    devices = circuit.native.mapped_mos(cells+bank, circuit.name(), mapping, 'XD')
    if not devices or any(d['limit_v'] != 1.95 for d in devices):
        raise ValueError('Missing complete native 1.8V device coverage')
    return cells, bank, devices, paths


def fixture(out, spec, devices):
    model = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    width = spec['input_slew_ps']/1e12/(2*np.arctanh(.8))
    wave = '+'.join(f'0.9*(tanh((time-{b+2.1:g}n)/{width:.17g})-tanh((time-{b+6.1:g}n)/{width:.17g}))' for b in (0, 10))
    rows = ['OpenLVDS '+VERSION, f'.lib "{model}" {spec["process"]}',
            f'.include "{out}/cells.spice"', f'.include "{out}/bank.spice"',
            f'.options device temp={spec["temperature"]}',
            '.options timeint method=gear reltol=1e-4 abstol=1e-12',
            'VDD VDD 0 1.8', 'BIN IN 0 V={'+wave+'}']
    for pin, value in circuit.encode(spec['coarse'], spec['fine']).items():
        rows.append(f'V{pin} {pin} 0 {1.8*value:g}')
    rows += ['XD '+' '.join('0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in circuit.ports())+' '+circuit.name(),
             f'CLOAD OUT 0 {spec["load_ff"]}f', '.tran 2p 20n 0 2p']
    probes = {'IN', 'OUT', 'VDD', *circuit.encode(spec['coarse'], spec['fine'])}
    probes.update(n for d in devices for n in d['terminals'] if n != '0')
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)), '.end', ''])


def measure(folder, spec, devices):
    def column(n):
        return 'v('+n.replace(':', '.').lower()+')'
    requested = {column(n) for d in devices for n in d['terminals'] if n != '0'}
    requested.update(column(n) for n in ['IN', 'OUT', *circuit.encode(spec['coarse'], spec['fine'])])
    names, w = validate(folder/'bench.raw', requested, 20e-9)
    idx = {n: i for i, n in enumerate(names)}
    t = w[:, idx['time']]*1e12
    if t[0] > 1e-6:
        raise ValueError('Native transient omits its startup interval')
    def get(n):
        return np.zeros(len(t)) if n == '0' else w[:, idx[column(n)]]
    samples = []
    for base in (0, 10000):
        window = (t >= base) & (t <= base+10000)
        sample = {}
        for up, label in ((True, 'rise'), (False, 'fall')):
            a = crossings(t[window], get('IN')[window], up)
            b = crossings(t[window], get('OUT')[window], up)
            if len(a) != 1 or len(b) != 1 or b[0] <= a[0]:
                raise ValueError('Missing/extra native output pulse or wrong epoch')
            sample[label+'_delay_ps'] = float(b[0]-a[0])
        samples.append(sample)
    stress = []
    for d in devices:
        peak = max(float(np.max(np.abs(get(a)-get(b)))) for a, b in itertools.combinations(d['terminals'], 2))
        stress.append(dict(device=d['name'], maximum_terminal_difference_v=peak,
                           limit_v=d['limit_v'], passed=bool(peak <= d['limit_v'])))
    controls = []
    stable = t >= 1500
    for pin, value in circuit.encode(spec['coarse'], spec['fine']).items():
        if np.max(np.abs(get(pin)-1.8*value)) > .01:
            raise ValueError('External control stimulus changed')
        i = int(pin[1:])
        nodes = [(f'XD:select{i}', value)] if pin[0] == 'S' else [(f'XD:fine{i}', value), (f'XD:fine_b{i}', 1-value)]
        for node, target in nodes:
            deviation = float(np.max(np.abs(get(node)[stable]-1.8*target)))
            controls.append(dict(node=node, deviation_v=deviation, passed=bool(deviation <= .18)))
    return dict(samples=samples, terminal_stress=stress,
                terminal_screen_passed=all(d['passed'] for d in stress), controls=controls,
                control_settling_passed=all(c['passed'] for c in controls),
                repeated_delay_difference_ps={k: abs(samples[1][k+'_delay_ps']-samples[0][k+'_delay_ps']) for k in ('rise', 'fall')},
                zero_code_fast_quarter_headroom_ps=(1e6/410/4-max(s[k] for s in samples for k in s)) if spec['coarse'] == spec['fine'] == 0 else None,
                qualified_phy=False, legal_code_table_admitted=False, scope=SCOPE)


def prepare(compound, fine, clock):
    if engine() != 'ngspice':
        raise ValueError('Require pinned native ngspice')
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A'
    sc = pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    cells, bank, devices, paths = libraries(compound, fine, clock, sc)
    # Bind imported transitive helpers and subprocess producers, without
    # freezing unrelated experiments added while this campaign is running.
    paths += sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
                     if getattr(module, '__file__', None)
                     and Path(module.__file__).resolve().parent == ROOT/'scripts'})
    paths += [ROOT/'scripts'/n for n in ('run_native_binary_v2.py', 'run_ngspice.py', 'spice_slots.py')]
    paths += [ROOT/'clocking_v2.json', ROOT/'clocking_duty_v2_2.json', ROOT/'build/tools/ngspice.json']
    models = [sc, pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity = dict(version=VERSION, compound=str(compound.relative_to(ROOT)), fine=str(fine.relative_to(ROOT)), clock=str(clock.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths}, pdk_files={str(p): sha(p) for p in models},
                    simulator=provenance(), specs=specifications(), devices=devices, max_workers=2, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    write(out/'cells.spice', cells); write(out/'bank.spice', bank)
    tasks = []
    for n, spec in enumerate(identity['specs']):
        folder = out/str(n); folder.mkdir()
        write(folder/'bench.cir', fixture(out, spec, devices))
        tasks.append(dict(id=str(n), spec=spec, deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
           libraries={n: sha(out/n) for n in ('cells.spice', 'bank.spice')}, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['max_workers'] != 2
            or engine() != 'ngspice' or provenance() != i['simulator']
            or any(sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(sha(Path(n)) != h for n, h in i['pdk_files'].items())
            or any(sha(out/n) != h for n, h in m['libraries'].items())
            or len(m['tasks']) != len(i['specs'])):
        raise ValueError('Uniform-tree native context changed')
    for n, task in enumerate(m['tasks']):
        folder = out/str(n)
        if (task['id'] != str(n) or task['spec'] != i['specs'][n]
                or sha(folder/'bench.cir') != task['deck_sha256']
                or (folder/'bench.cir').read_text() != fixture(out, task['spec'], i['devices'])):
            raise ValueError('Uniform-tree native task changed')
    return m


def run(out):
    m = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior native run')
        atomic(out/'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out/task['id']; result = error = None
            try:
                with lease(ROOT, priority=0, label=CONTEXT+'_'+task['id']):
                    bound(out)
                    p = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'), '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                write(folder/'console.log', p.stdout+p.stderr)
                p.check_returncode()
                result = measure(folder, task['spec'], m['identity']['devices'])
            except Exception as e:
                error = str(e)
            row = dict(task=task, result=result, error=error, files={p.name: sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, m['tasks']))
        bound(out)
        atomic(out/'summary.json', dict(rows=rows, qualified_phy=False, scope=SCOPE))
        atomic(out/'state.json', dict(status='complete', cases=len(rows), errors=sum(r['error'] is not None for r in rows), qualified_phy=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path, nargs='?')
    p.add_argument('--compound', type=Path); p.add_argument('--fine', type=Path)
    p.add_argument('--clock', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        if a.compound is None or a.fine is None or a.clock is None:
            p.error('Provide component, fine and clock RC receipts')
        print(prepare(a.compound.resolve(), a.fine.resolve(), a.clock.resolve()), flush=True)
    else:
        if a.artifact is None:
            p.error('Provide prepared artifact')
        run(a.artifact.resolve())
