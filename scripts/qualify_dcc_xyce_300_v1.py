#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh Xyce baseline/INV8 unequal-slew pilot with numerical refinement.

Source DCC diagnostic only. Never grants physical/DLL/PHY admission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import numpy as np
import xyce_profile_300 as xyce
from dcc_source_300 import model_closure
import dcc_input_waveforms_300_v2 as waveform
import dcc_inv8_fixture_300_v1 as fixture
import dcc_source_measure_300_v2 as source_measure
import dcc_chain_fanout_300_v1 as inventory
from run_native_binary_v2 import translate
from native_binary_raw_v2 import validate
from xyce_raw_aliases_v148 import normalize
from spice_dispatch import lease
from replay_bank_300_v2 import same

ROOT = xyce.ROOT
CONTEXT = 'dcc_xyce_300_v1'
DONORS = {
    'baseline': ROOT / 'build/diagnostics/dcc_corrected_input_pilot_300_v2/bef3db10942b26f2',
    'inv8': ROOT / 'build/diagnostics/dcc_inv8_output_pilot_300_v1/2644642a8fe621b9',
}


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def specs():
    return [dict(process='sf', temperature=40, mhz=310, r_duty=d, f_duty=d,
                 r_slew_10_90_ps=a, f_slew_10_90_ps=b, phase_error_ps=0, cycles=18)
            for d in (.6, .4) for a, b in ((20, 250), (250, 20), (250, 250), (20, 20))]


def native_fixture(library, spec, circuit, variant):
    ports = ['P0','P180','RESET_N','Q','VDD','VSS']
    devices, resistors = inventory.mapped_mos(circuit,dict(zip(ports,ports[:-1]+['0'])),'XD')
    expected = 136 if variant=='baseline' else 144
    if len(devices)!=expected or len(resistors)!=2:
        raise ValueError('Native variant inventory changed')
    observations = dict(devices=devices, passive_resistors=resistors)
    text = waveform.fixture(library,spec)
    nodes = {'RESET_N'} | {n for d in devices+resistors for n in d['terminals'] if n!='0'}
    match = re.search(r'(?m)^\.print tran (.+)$',text)
    if match is None:
        raise ValueError('Source observations missing')
    tokens = match[1].split()+['V('+n+')' for n in sorted(nodes)]
    unique = {token.lower().replace(':','.'):token for token in tokens}
    text = text[:match.start()]+'.print tran '+' '.join(unique.values())+text[match.end():]
    translate(text)
    return text, observations


def measure(names, w, spec, observations, independent=False):
    result = source_measure.measure(names,w,spec,independent=independent)
    index = {n:k for k,n in enumerate(names)}
    def get(node):
        return np.zeros(len(w)) if node=='0' else w[:,index['v('+node.lower().replace(':','.')+')']]
    stress = []
    for device in observations['devices']:
        volts = [get(n) for n in device['terminals']]
        if independent:
            import itertools
            span = max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(volts,2))
        else:
            span = float(np.max(np.ptp(np.stack(volts),axis=0)))
        stress.append(dict(device=device['name'],maximum_terminal_span_v=span,
                           limit_v=device['limit_v'],passed=span<=device['limit_v']))
    reset = float(np.max(np.abs(get('RESET_N')-1.8*np.clip((w[:,index['time']]*1e12-1000)/20,0,1))))
    passed = all(d['passed'] for d in stress)
    return dict(source=result, native_mos=len(stress), terminal_stress=stress,
                native_terminal_stress_passed=passed, maximum_reset_error_v=reset,
                source_screen_passed=bool(result['source_screen_passed'] and passed and reset<=1e-9))


def prepare():
    runtime = xyce.runtime()
    inputs = {str(p): xyce.sha(p) for donor in DONORS.values()
              for p in [donor/'cells.spice', donor/'hold1.spice', donor/'manifest.json']}
    model = Path('/opt/pdk/ciel/sky130/versions/1689ac3f2dc763876eaf967227c7dfe831b031ae/sky130A/libs.tech/ngspice/sky130.lib.spice')
    inputs.update(model_closure(model))
    helpers = {Path(m.__file__).resolve() for m in list(sys.modules.values())
               if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'}
    helpers.update([Path(__file__).resolve(), ROOT/'clocking_300mhz.json'])
    inputs.update({str(p): xyce.sha(p) for p in helpers})
    identity = dict(version=CONTEXT, inputs=inputs, runtime=runtime, profiles=xyce.PROFILES,
                    specs=specs(), max_workers=2, priority=2, timeout_seconds=900,
                    historical_timing_reused=False, qualified_phy=False)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT/'build/diagnostics'/CONTEXT/key
    out.mkdir(parents=True, exist_ok=False)
    tasks = []
    for variant, donor in DONORS.items():
        library = out/variant
        library.mkdir()
        for name in ('cells.spice', 'hold1.spice'):
            original = (donor/name).read_text()
            adapted = '\n'.join(line.split('$', 1)[0].rstrip() for line in original.splitlines())+'\n'
            if [x.split('$', 1)[0].split() for x in original.splitlines() if x.split('$', 1)[0].strip()] != [x.split() for x in adapted.splitlines() if x.strip()]:
                raise ValueError('Circuit tokens changed')
            (library/name).write_text(adapted)
        circuit = (library/'cells.spice').read_text()+'\n'+(library/'hold1.spice').read_text()
        for k, spec in enumerate(specs()):
            text, observations = native_fixture(library, spec, circuit, variant)
            for profile in xyce.PROFILES:
                number = str(len(tasks))
                folder = out/number
                folder.mkdir()
                deck = re.sub(r'(?m)^\.options timeint .*\n', xyce.options(profile), text)
                step = xyce.PROFILES[profile]['maxstep_ps']
                deck, count = re.subn(r'(?m)^\.tran 1p (\S+) 0 1p$', f'.tran {step}p \\1 0 {step}p', deck)
                if count != 1:
                    raise ValueError('Require exact source transient')
                deck = deck.replace('.print tran ', f'.print tran format=raw precision=17 file={folder}/bench.xyce.raw ')
                (folder/'bench.cir').write_text(deck)
                tasks.append(dict(id=number, variant=variant, spec_index=k, spec=spec, profile=profile,
                                  stop=waveform.capture_stop_ps(spec)*1e-12, observations=observations,
                                  deck_sha256=xyce.sha(folder/'bench.cir')))
    files = {str(p): xyce.sha(p) for p in out.rglob('*.spice')}
    files.update({str(out/t['id']/'bench.cir'):t['deck_sha256'] for t in tasks})
    save(out/'manifest.json', dict(identity=identity, tasks=tasks, files=files, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text())
    identity = m['identity']
    if out.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]:
        raise ValueError('Campaign identity changed')
    if identity['runtime'] != xyce.runtime() or identity['specs'] != specs() or identity['profiles'] != xyce.PROFILES:
        raise ValueError('Runtime, profile or coverage changed')
    if len(m['tasks']) != 48 or len({t['id'] for t in m['tasks']}) != 48:
        raise ValueError('Incomplete task coverage')
    for name, digest in {**identity['inputs'], **identity['runtime']['files'], **m['files']}.items():
        if xyce.sha(name) != digest:
            raise ValueError('Captured file changed: '+name)
    return m


def crossing_times(names, w, node, up):
    t = w[:, names.index('time')]
    v = w[:, names.index('v('+node+')')]
    indices = np.flatnonzero((v[:-1]<.9)&(v[1:]>=.9) if up else (v[:-1]>.9)&(v[1:]<=.9))
    return t[indices]+(.9-v[indices])*(t[indices+1]-t[indices])/(v[indices+1]-v[indices])


def refinement(out, rows):
    groups = []
    for variant in DONORS:
        for index in range(8):
            members = [r for r in rows if r['task']['variant']==variant and r['task']['spec_index']==index]
            result = dict(variant=variant, spec_index=index, complete=False, passed=False)
            if len(members)==3 and all(r['error'] is None for r in members):
                reference = next(r for r in members if r['task']['profile']=='strict')
                ns, w = validate(out/reference['task']['id']/'bench.raw', set(), reference['task']['stop'])
                comparisons = []
                for member in members:
                    names, data = validate(out/member['task']['id']/'bench.raw', set(), member['task']['stop'])
                    deltas = []
                    matched = True
                    for node in ('p0','p180','q'):
                        for up in (True,False):
                            a, b = crossing_times(ns,w,node,up), crossing_times(names,data,node,up)
                            matched &= len(a)==len(b) and len(a)>0
                            if len(a)==len(b):
                                deltas.extend(abs(b-a)*1e12)
                    dc = max(abs(float(data[0,names.index(n)]-w[0,ns.index(n)])) for n in names if n!='time')
                    comparisons.append(dict(profile=member['task']['profile'], matched_events=bool(matched),
                                            maximum_edge_difference_ps=float(max(deltas)) if deltas else None,
                                            maximum_dc_difference_v=dc,
                                            passed=bool(matched and deltas and max(deltas)<=1 and dc<=.001)))
                result.update(complete=True, comparisons=comparisons,
                              passed=all(c['passed'] for c in comparisons))
            groups.append(result)
    return groups


def run(out):
    m = bound(out)
    state = out/'state.json'
    with state.open('x') as f:
        json.dump(dict(status='running', qualified_phy=False), f)
    def one(task):
        folder = out/task['id']
        row = dict(task=task, error=None, complete=False, qualified_phy=False)
        start = time.monotonic()
        try:
            with lease(ROOT, priority=2, label=CONTEXT+'_'+task['id']):
                command = xyce.command(folder/'native.log', folder/'bench.cir')
                row['command'] = command
                with (folder/'console.log').open('w') as log:
                    process = subprocess.run(command, cwd=folder, env=xyce.environment(), stdout=log,
                                             stderr=subprocess.STDOUT, timeout=m['identity']['timeout_seconds'])
                row['returncode'] = process.returncode
                if process.returncode:
                    raise ValueError('Xyce returned '+str(process.returncode))
            row['normalization'] = normalize(folder/'bench.xyce.raw', folder/'bench.raw')
            names, w = validate(folder/'bench.raw', set(), task['stop'])
            result = measure(names,w,task['spec'],task['observations'])
            independent = measure(names,w,task['spec'],task['observations'],independent=True)
            if not same(result, independent):
                raise ValueError('Independent DCC metrology differs')
            row.update(complete=True, result=result, independent_result=independent)
        except Exception as exc:
            row['error'] = str(exc)
        row['wall_seconds'] = time.monotonic()-start
        logs = '\n'.join(p.read_text(errors='replace') for p in (folder/'native.log',folder/'console.log') if p.exists())
        row['warnings'] = xyce.warnings(logs)
        row['files'] = {p.name:xyce.sha(p) for p in folder.iterdir() if p.is_file()}
        save(folder/'summary.json',row)
        return row
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(one, t) for t in m['tasks']]
        for future in as_completed(futures):
            rows.append(future.result())
            save(out/'progress.json', dict(completed=len(rows), total=48, errors=sum(r['error'] is not None for r in rows), qualified_phy=False))
    rows.sort(key=lambda r:int(r['task']['id']))
    bound(out)
    save(out/'summary.json', dict(rows=rows, refinement=refinement(out,rows), qualified_phy=False,
                                 scope='SF40 310 MHz unequal-slew source DCC diagnostic; full PVT/physical/loaded DLL not admitted'))
    save(state, dict(status='complete', cases=48, errors=sum(r['error'] is not None for r in rows), qualified_phy=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare','run'])
    p.add_argument('artifact', type=Path, nargs='?')
    a = p.parse_args()
    if a.action=='prepare':
        print(prepare(), flush=True)
    elif a.artifact is None:
        p.error('Supply fresh artifact')
    else:
        run(a.artifact.resolve())
