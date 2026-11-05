#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched two-buffer clock-drive experiment for routed-pair phase qualification.

Duplicate the complete certified native BUF8 RC, retaining all counter/load
devices and every acceptance limit. Shared inter-driver wires are ideal until
physical integration; this experiment cannot admit a clock island or PHY.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import probe_static_phase_clock_release_v6 as original
import verify_static_phase_clock_release_v6 as baseline_verification
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=original.ROOT
VERSION='matched-native-two-buffer-routed-pair-clock-drive-v2.1'
CONTEXT='static_phase_clock_drive_v2'
specifications=original.specifications


def strengthen(text):
    rows=re.findall(r'(?m)^Xclock_driver [^\n]+$',text)
    if len(rows)!=1 or 'Xclock_driver_parallel' in text:raise ValueError('Require exactly one original harness clock driver')
    words=rows[0].split()
    if (words[-1]!=original.circuit.components.CLOCK_BUFFER or words.count('RCLK')!=1 or words.count('CLK')!=1):
        raise ValueError('Native clock driver model or public clock nets changed')
    extra='Xclock_driver_parallel '+' '.join(words[1:])
    return text.replace(rows[0],rows[0]+'\n'+extra,1)


def check_devices(before,after):
    old={d['name']:d for d in before};new={d['name']:d for d in after}
    if len(old)!=len(before) or len(new)!=len(after) or any(new.get(n)!=d for n,d in old.items()):
        raise ValueError('Original native device/terminal/limit witness changed')
    prefix='XD:Xclock_driver:';replacement='XD:Xclock_driver_parallel:'
    clones=[]
    for d in before:
        if d['name'].startswith(prefix):
            clone=dict(d,name=d['name'].replace(prefix,replacement,1),
                       terminals=[n.replace(prefix,replacement,1) if n.startswith(prefix) else n for n in d['terminals']])
            clones.append(clone)
    if not clones or {n:d for n,d in new.items() if n not in old}!={d['name']:d for d in clones}:
        raise ValueError('Added clock-driver RC did not produce exactly one private native MOS copy')
    return len(clones)


def checked_baseline(receipt):
    r=json.loads((receipt/'summary.json').read_text());i=r['identity']
    if (receipt.parent!=ROOT/'build/diagnostics/static_phase_release_verification_v6'
        or i['version']!=baseline_verification.VERSION
        or receipt.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or r['all_declared_raw_waveforms_verified'] is not True
        or any(sha(ROOT/n)!=h for n,h in {**i['witnesses'],**i['code']}.items())):
        raise ValueError('Require exact independently verified routed-pair baseline')
    parent=ROOT/i['parent'];m=original.bound(parent);state=json.loads((parent/'state.json').read_text())
    if (state['status']!='static_phase_pilot_complete' or state['cases']!=4 or state['errors']
        or m['identity']['specs']!=specifications()):raise ValueError('Require all four completed numerical baseline cases')
    baseline_verification.regenerate(parent,m)
    return parent,m,r


def libraries(parent,m):
    cells=(parent/'cells.spice').read_text();module=strengthen((parent/'pair.spice').read_text())
    devices=original.circuit.components.mapped_mos(cells+module,original.HARNESS,
        dict(RCLK='RCLK',REQUEST='REQUEST',PREPARE='PREPARE',RESET_N='RESET_N',CLK='CLK',VPWR='VDD',VGND='0'),'XD')
    added=check_devices(m['identity']['devices']['pair'],devices)
    return cells,module,devices,added


def fixture(out,spec,devices):
    deck=original.fixture(out,spec,devices);first,rest=deck.split('\n',1)
    if first!='OpenLVDS '+original.VERSION:raise ValueError('Baseline clock-drive fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+rest


def measure(folder,spec,devices):
    result=original.measure(folder,spec,devices)
    nodes=['low0','low1','armed'];required={'v(clk)',*['v(xd.xr.'+n+')' for n in nodes]}
    names,w=validate(folder/'bench.raw',required,26e-9);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12
    values={}
    for n in nodes:
        edges=crossings(t,w[:,idx['v(xd.xr.'+n+')']])
        if not len(edges):raise ValueError('Missing native low-phase assertion')
        values[n]=float(np.interp(edges[0],t,w[:,idx['v(clk)']]))
    result.update(clock_at_low_phase_assertion_v=values,minimum_clock_low_voltage_margin_v=.18-max(values.values()),
        scope='Two complete native BUF8 RC drivers feeding the unchanged routed-pair phase counter and reset loads; ideal shared inter-driver wires, no joint DCC first event, whole-clock layout, all-PVT, hardware warmup or PHY admission')
    return result


def prepare(receipt):
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice engine')
    parent,m,report=checked_baseline(receipt);cells,module,devices,added=libraries(parent,m)
    paths=[receipt/'summary.json',parent/'manifest.json',parent/'state.json',parent/'summary.json',parent/'cells.spice',parent/'pair.spice']
    paths += [ROOT/n for n in {**report['identity']['witnesses'],**report['identity']['code']}]
    paths += [ROOT/n for n in m['identity']['inputs']]
    paths += [Path(__file__),Path(original.__file__),Path(baseline_verification.__file__),ROOT/'scripts/native_binary_raw_v2.py',
              ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/probe_digital_dcc_v2.py']
    identity=dict(version=VERSION,baseline=str(parent.relative_to(ROOT)),receipt=str(receipt.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files=m['identity']['pdk_files'],simulator=provenance(),
        specs=specifications(),devices=devices,added_clock_driver_mos=added,clock_drivers=2,maximum_step_ps=1,
        original_native_devices_preserved=True,shared_inter_driver_wires='ideal diagnostic assembly')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'cells.spice',cells);write(out/'pair.spice',module);tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in ['cells.spice','pair.spice']},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or engine()!='ngspice' or provenance()!=i['simulator'] or i['specs']!=specifications()
        or i['clock_drivers']!=2 or not i['original_native_devices_preserved']
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=4):raise ValueError('Native clock-drive context changed')
    for n,task in enumerate(m['tasks']):
        if (task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']
            or (out/str(n)/'bench.cir').read_text()!=fixture(out,task['spec'],i['devices'])):raise ValueError('Native clock-drive deck/task changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native clock-drive experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],m['identity']['devices'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='clock_drive_pilot_complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    else:run(out)
