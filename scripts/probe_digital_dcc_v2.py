#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source-cell DCC feasibility; never physical or closed-loop admission.

The ideal phase stimuli isolate the pulse/OR/toggle circuit only. They are not
used as the clock source for any native link or claimed DLL qualification.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess

import numpy as np
from spice_dispatch import lease
from spice_engine import command, provenance
from run_ngspice import read_raw

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'source-digital-dcc-v2.1'
CELLS = ('buf_1', 'inv_1', 'and2_1', 'or2_1', 'dfrtp_1')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    if path.exists(): raise ValueError('Retain prior evidence: ' + str(path))
    path.write_text(value)


def atomic(path, value):
    tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(value, indent=2)+'\n'); tmp.replace(path)


def cell_library(pdk):
    text = pdk.read_text(); blocks = []
    for name in CELLS:
        found = re.findall(r'(?ims)^\.subckt\s+sky130_fd_sc_hd__'+name+r'\s[^\n]*\n.*?^\.ends\b[^\n]*', text)
        if len(found) != 1: raise ValueError('Missing/duplicate native cell ' + name)
        blocks += found
    return '\n'.join(blocks)+'\n'


def circuit(buffers):
    if buffers not in (0, 2, 4): raise ValueError('Undeclared pulse variant')
    s = ['.subckt dcc_source P0 P180 RESET_N Q VDD VSS']
    for tag, phase in [('a', 'P0'), ('b', 'P180')]:
        node = tag
        for i in range(buffers):
            nxt = f'{tag}_d{i}'; s += [f'X{tag}buf{i} {node} VSS VSS VDD VDD {nxt} sky130_fd_sc_hd__buf_1']; node = nxt
        s += [f'X{tag}inv {node} VSS VSS VDD VDD {tag}n sky130_fd_sc_hd__inv_1',
              f'X{tag}clear RESET_N {tag}n VSS VSS VDD VDD {tag}reset sky130_fd_sc_hd__and2_1',
              f'X{tag}ff {phase} VDD {tag}reset VSS VSS VDD VDD {tag} sky130_fd_sc_hd__dfrtp_1']
    s += ['Xor a b VSS VSS VDD VDD events sky130_fd_sc_hd__or2_1',
          'Xinv Q VSS VSS VDD VDD feedback sky130_fd_sc_hd__inv_1',
          'Xtoggle events feedback RESET_N VSS VSS VDD VDD Q sky130_fd_sc_hd__dfrtp_1', '.ends dcc_source']
    return '\n'.join(s)+'\n'


def fixture(out, spec, lib):
    period = 1000/spec['mhz']; slew = spec['slew_ps']/1000
    spacing = period/2 + spec['phase_error_ps']/1000
    # PULSE rise-to-rise spacing is independent of phase duty; start/reset
    # offset avoids reset release at a valid input edge.
    model = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    return (f'OpenLVDS {VERSION} source-only\n.lib "{model}" {spec["process"]}\n'
        f'.include "{out}/cells.spice"\n.include "{out}/{lib}"\n'
        f'.options device temp={spec["temperature"]}\n.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
        'VDD VDD 0 1.8\nVR RESET_N 0 PWL(0 0 1n 0 1.02n 1.8)\n'
        f'VP0 P0 0 PULSE(0 1.8 2n {slew}n {slew}n {period*.3-slew}n {period}n)\n'
        f'VP1 P180 0 PULSE(0 1.8 {2+spacing}n {slew}n {slew}n {period*.7-slew}n {period}n)\n'
        'XD P0 P180 RESET_N Q VDD 0 dcc_source\nCQ Q 0 20f\n'
        f'.tran 1p {2+period*18}n 0 1p\n'
        '.print tran V(P0) V(P180) V(Q) V(XD:a) V(XD:b) V(XD:events) V(XD:feedback) '
        'V(XD:areset) V(XD:breset) V(VDD)\n.end\n')


def crossings(t, v, rising=True):
    mask = ((v[:-1] < .9) & (v[1:] >= .9)) if rising else ((v[:-1] > .9) & (v[1:] <= .9))
    idx = np.flatnonzero(mask)
    return t[idx] + (.9-v[idx])*(t[idx+1]-t[idx])/(v[idx+1]-v[idx])


def measure(folder, spec):
    names, w = read_raw(folder/'bench.raw'); t = w[:, names.index('time')]*1e12
    if not np.isfinite(w).all() or t[-1] < (2+1000/spec['mhz']*18)*1000-.01:
        raise ValueError('Incomplete/nonfinite waveform')
    get = lambda n: w[:, names.index('v('+n+')')]
    start, end = 10000, 40000
    edges = lambda n, up=True: crossings(t, get(n), up)
    window = lambda a: a[(a >= start) & (a < end)]
    source = np.sort(np.concatenate([edges('p0'), edges('p180')]))
    event = edges('xd.events'); output = np.sort(np.concatenate([edges('q'), edges('q', False)]))
    selected = window(source)
    # Each source event must cause exactly one event and one output transition,
    # with positive bounded latency. Match each source's own next-event window.
    count_ok = True; latencies = []
    for a in selected:
        following = source[source > a+.01]; b = following[0] if len(following) else a+1000
        ev = event[(event > a) & (event < b)]; q = output[(output > a) & (output < b)]
        if len(ev) != 1 or len(q) != 1: count_ok = False
        else: latencies.append(float(q[0]-a))
    pulse_widths = {}
    for label in ('xd.a', 'xd.b', 'xd.events'):
        rising, falling = edges(label), edges(label, False); widths = []
        for a in window(rising):
            b = falling[falling > a]
            if len(b): widths.append(float(b[0]-a))
        pulse_widths[label] = min(widths) if widths else None
    qrise = edges('q'); qfall = edges('q', False); high=[]; low=[]
    for a in window(qrise):
        nxt=qfall[qfall>a]
        if len(nxt): high.append(nxt[0]-a)
    for a in window(qfall):
        nxt=qrise[qrise>a]
        if len(nxt): low.append(nxt[0]-a)
    # Deliberate phase errors test event handling; symmetry is judged only on
    # equally spaced input events. No claim of filtering input timing error.
    half_error = max(abs(np.mean(high)-500000/spec['mhz']), abs(np.mean(low)-500000/spec['mhz'])) if high and low else None
    stress = max(float(np.max(np.abs(get(n)))) for n in ['q','xd.a','xd.b','xd.events','xd.feedback','xd.areset','xd.breset'])
    return dict(event_integrity_passed=bool(count_ok and len(selected)>16),
        source_events=len(selected), minimum_source_spacing_ps=float(np.min(np.diff(source))),
        minimum_pulse_width_ps=pulse_widths, output_latency_range_ps=[min(latencies),max(latencies)] if latencies else None,
        mean_half_cycle_error_ps=float(half_error) if half_error is not None else None,
        symmetric_timing_passed=bool(half_error is not None and half_error <= 50) if spec['phase_error_ps']==0 else None,
        observed_node_abs_max_v=stress, qualified_phy=False,
        scope='Source-cell pulse/event feasibility only; no physical RC, DLL, terminal-stress or PHY admission')


def prepare(smoke=False):
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    policy=ROOT/'clocking_v2.json'
    code={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__), ROOT/'sky130/v2/openlvds_dcc_v2.v', policy,
         ROOT/'scripts/spice_dispatch.py', ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_engine.py']}
    specs=[dict(process=p,temperature=t,mhz=f,slew_ps=s,phase_error_ps=e,buffers=b)
        for p,t,f,s,e,b in (itertools.product(['ss'],[40],[410],[20,250],[0,-140],[0,2,4]) if smoke else
        itertools.product(['tt','ff','ss','fs','sf'],[0,25,40],[390,400,410],[20,200,250],[0,-140,140],[0,2,4]))]
    identity=dict(version=VERSION, code=code, pdk=str(pdk), pdk_sha256=sha(pdk), simulator=provenance(), specs=specs)
    out=ROOT/'build/diagnostics/digital_dcc_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    write(out/'cells.spice',cell_library(pdk))
    for b in (0,2,4): write(out/f'dcc_b{b}.spice',circuit(b))
    tasks=[]
    for i,spec in enumerate(specs):
        folder=out/str(i); folder.mkdir(); write(folder/'bench.cir',fixture(out,spec,f'dcc_b{spec["buffers"]}.spice'))
        tasks.append(dict(id=str(i),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text()); i=m['identity']
    if (out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['simulator']!=provenance() or sha(Path(i['pdk']))!=i['pdk_sha256']
        or any(sha(ROOT/n)!=h for n,h in i['code'].items())
        or any(sha(out/n)!=h for n,h in m['libraries'].items())):
        raise ValueError('Source DCC context changed')
    for task in m['tasks']:
        if sha(out/task['id']/'bench.cir')!=task['deck_sha256']: raise ValueError('Changed DCC deck')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists(): raise ValueError('Retain prior execution')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id']; result=error=None
            try:
                with lease(ROOT,priority=0,label='dcc_v2_'+task['id']):
                    bound(out)
                    process=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',process.stdout+process.stderr); process.check_returncode()
                result=measure(folder,task['spec'])
            except Exception as e: error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row); return row
        with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(execute,m['tasks']))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='source_screen_complete',cases=len(rows),
            errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound'])
    p.add_argument('artifact',type=Path,nargs='?');p.add_argument('--smoke',action='store_true');a=p.parse_args()
    if a.action=='prepare': print(prepare(a.smoke),flush=True)
    elif a.artifact is None: p.error('Require artifact')
    elif a.action=='run':run(a.artifact.resolve())
    else: print(json.dumps(bound(a.artifact.resolve()),indent=2))
