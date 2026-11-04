#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare a full bank using native guard-pair, fine-cell and fine-driver RC.

The complete sixteen-choice coarse topology remains. Probe both sides of the
15->16 carry and repeat code zero. Coarse-control/shared-MIM/common-wire physical proofs, dense codes, periodic
clocks, full PVT and PHY qualification remain open.
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
import dcdl_weighted_direct_v3 as circuit
import probe_weighted_fine_bank_v2 as previous
import guard_pair_release_rc_families_v2 as families
import weighted_fine_rc_families_v2 as fine_families
import weighted_bank_control_gate_v2 as control_gate
from build_compound_drivers_v3 import cell_definition
from probe_digital_dcc_v2 import sha,write,atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=previous.ROOT
VERSION='direct-weighted-native-pair-fine-and-control-rc-pilot-v2.2'
CONTEXT='weighted_direct_v3'
CODES=[0,1,15,16,31,0]


def specifications():
    return [dict(variant=v,process='ss',temperature=40,coarse=c,codes=list(CODES),
                 control_slew_ps=20,input_slew_ps=100,load_ff=20)
            for v,c in itertools.product(circuit.MODES,[0,1])]


def libraries(compound,guard,fines,clock,sc):
    cells={};paths=[]
    for parent in [compound,guard,clock]:
        group,files=families.witnesses(parent)
        if set(group)&set(cells):raise ValueError('Duplicate native component')
        cells.update(group);paths+=files
    group,files=fine_families.witnesses(fines)
    if set(group)&set(cells):raise ValueError('Duplicate physical fine component')
    cells.update(group);paths+=files
    texts=[cells[n]['text'].rstrip() for n in sorted(cells)];orders={n:c['info']['ports'] for n,c in cells.items()}
    library=sc.read_text()
    for short in ['conb_1','buf_4']:
        name=circuit.direct.native.SC+short;text=cell_definition(library,name);texts.append(text.rstrip())
        orders[name]=circuit.parsing.definitions(text)[name][0]
    cell_text='\n'.join(texts)+'\n';modules={v+'.spice':circuit.source(v,orders) for v in circuit.MODES}
    devices={v:circuit.devices(cell_text+modules[v+'.spice']) for v in circuit.MODES}
    modules['cells.spice']=cell_text
    return modules,orders,devices,paths


def fixture(out,spec,devices):
    deck=previous.fixture(out,spec,devices)
    if deck.count('V(XD:r0)')!=1:raise ValueError('Weighted fixture internal output probe changed')
    deck=deck.replace('V(XD:r0)','').replace(' '+previous.circuit.NAME+'\n',' '+circuit.NAME+'\n')
    first,rest=deck.split('\n',1)
    if first!='OpenLVDS '+previous.VERSION:raise ValueError('Weighted fixture title changed')
    return 'OpenLVDS '+VERSION+'\n.options itl4=100\n'+rest


def measure(folder,spec,devices):
    result=previous.measure(folder,spec,devices)
    result['scope']='Full sixteen-choice direct-port bank with actual routed guard-pair, five fine-cell and guarded fine-driver RC; source coarse controls/shared base MIM, ideal common wires; sparse carry/repeat only, no whole-bank RC, dense codes, periodic clocks, full-PVT or PHY admission'
    return result


def prepare(compound,guard,fines,clock):
    if engine()!='ngspice':raise ValueError('Use the explicitly pinned ngspice engine')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    modules,orders,devices,paths=libraries(compound,guard,fines,clock,sc)
    code=[Path(__file__),Path(circuit.__file__),Path(control_gate.__file__),Path(control_gate.verification.__file__),Path(control_gate.verification.pilot.__file__),Path(previous.__file__),Path(families.__file__),Path(fine_families.__file__),Path(circuit.previous.__file__),Path(circuit.pair.__file__),Path(circuit.controls.__file__),Path(circuit.controls.unit.__file__),
          ROOT/'scripts/dcdl_weighted_fine_v2.py',ROOT/'scripts/dcdl_mim_bank_direct_v2.py',ROOT/'scripts/dcdl_mim_bank_physical_v2.py',ROOT/'scripts/dcdl_mim_bank_v2.py',
          ROOT/'scripts/phase_release_rc_families_v2.py',ROOT/'scripts/static_phase_clock_release_v5.py',ROOT/'scripts/native_clock_components_v2.py',ROOT/'scripts/native_clock_components_v3.py',
          ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/native_binary_raw_v2.py',
          ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'clocking_v2.json']
    models=[sc,pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity=dict(version=VERSION,compound=str(compound.relative_to(ROOT)),guard=str(guard.relative_to(ROOT)),fine_cells=str(fines.relative_to(ROOT)),clock=str(clock.relative_to(ROOT)),source_library=str(sc),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code},pdk_files={str(p):sha(p) for p in models},simulator=provenance(),
        specs=specifications(),devices=devices,orders=orders,execution_prerequisite='independent-physical-fine-control-v3-guarded-both-biases',maximum_step_ps=2,itl4=100,total_fine_mim_area_um2=186,
        scope='SS40 410MHz-quarter-range sparse architecture screen; actual routed guard pairs, fine-cell and fine-driver RC; source coarse controls/shared MIM, ideal common wires, no whole-bank or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n,text in modules.items():write(out/n,text)
    tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,devices[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in modules},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or any(sha(out/n)!=h for n,h in m['libraries'].items())
        or i['specs']!=specifications() or len(m['tasks'])!=len(i['specs'])):raise ValueError('Weighted direct context changed')
    for n,t in enumerate(m['tasks']):
        if t['id']!=str(n) or t['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=t['deck_sha256']:raise ValueError('Weighted direct task changed')
    return m


def run(out,control_receipt):
    m=bound(out)
    proof=control_gate.require(control_receipt,ROOT/m['identity']['clock'],ROOT/m['identity']['fine_cells'])
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior direct weighted run')
        atomic(out/'control_gate.json',proof)
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out)
                    if control_gate.require(control_receipt,ROOT/m['identity']['clock'],ROOT/m['identity']['fine_cells'])!=proof:raise ValueError('Fine-control admission changed')
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode()
                result=measure(folder,task['spec'],m['identity']['devices'][task['spec']['variant']])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='weighted_direct_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--guard',type=Path);p.add_argument('--fine-cells',type=Path);p.add_argument('--clock-cells',type=Path);p.add_argument('--control-receipt',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if any(v is None for v in [a.guard,a.fine_cells,a.clock_cells]):p.error('Provide independently verified guard-pair, fine-cell and fine-driver RC')
        print(prepare(a.artifact.resolve(),a.guard.resolve(),a.fine_cells.resolve(),a.clock_cells.resolve()),flush=True)
    else:
        if a.control_receipt is None:p.error('Provide a passing independent physical fine-control receipt before running the full bank')
        run(a.artifact.resolve(),a.control_receipt.resolve())
