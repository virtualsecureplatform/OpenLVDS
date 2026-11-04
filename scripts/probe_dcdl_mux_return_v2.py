#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare a source return-mux core with real forward/fine component RC.

Full sixteen-coarse/thirty-one-fine topology, two isolated pulses and every
native MOS terminal are retained. Mux, turn, control and common-wire RC still
need fresh physical proof; this cannot admit a legal-code ROM or PHY model.
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
import dcdl_mux_return_v2 as circuit
import phase_release_rc_families_v2 as families
import native_clock_components_v2 as parsing
import probe_routed_dcdl_bank_v2 as pulses
from audit_passive_rc_v3 import audit
from build_compound_drivers_v3 import cell_definition
from lvs_utils import clean_match
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic
from spice_library import checked_netlist
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=pulses.ROOT
VERSION='native-source-return-mux-forward-and-fine-rc-pilot-v2.1'


def specifications():return pulses.specifications()


def libraries(compound,fine,sc):
    rc,paths=families.witnesses(compound)
    proof=json.loads((fine/'summary.json').read_text());i=proof['identity'];info=proof['verified_model']
    if (fine.parent!=ROOT/'build/diagnostics/mim_switch_2x3_verification_v2'
        or fine.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or not proof['rc_topology_passed'] or not clean_match((fine/'lvs.log').read_text())
        or any(sha(ROOT/n)!=h for n,h in {**i['witnesses'],**i['code']}.items())):
        raise ValueError('Require exact independently verified fine-unit RC')
    text=checked_netlist(info)
    if not audit(text)['elementwise_passive_passed']:raise ValueError('Require passive fine-unit RC')
    if info['header']!='.subckt '+circuit.fine.NAME+' NODE EN ENB VDD VSS':raise ValueError('Fine-unit interface changed')
    rc[circuit.fine.NAME]=dict(info=info,text=text)
    paths += [fine/'summary.json',fine/'lvs.log',*[ROOT/n for n in {**i['witnesses'],**i['code']}]]
    texts=[rc[n]['text'].rstrip() for n in sorted(rc)];orders={n:rc[n]['info']['ports'] for n in rc}
    library=sc.read_text()
    for short in ['buf_4','buf_1','inv_1','inv_4','mux2i_4']:
        model=circuit.SC+short;block=cell_definition(library,model)
        texts.append(block.rstrip());orders[model]=parsing.definitions(block)[model][0]
    cells='\n'.join(texts)+'\n';bank=circuit.source(orders)
    devices=parsing.mapped_mos(cells+bank,circuit.NAME,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in circuit.PORTS},'XD')
    return cells,bank,orders,devices,paths


def fixture(out,spec,devices):
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    rows=[f'OpenLVDS {VERSION}',f'.lib "{model}" {spec["process"]}',f'.include "{out}/cells.spice"',f'.include "{out}/bank.spice"',
          f'.options device temp={spec["temperature"]}', '.options timeint method=gear reltol=1e-4 abstol=1e-12','VDD VDD 0 1.8']
    width=spec['input_slew_ps']/1e12/(2*np.arctanh(.8))
    wave=[f'0.9*(tanh((time-{base+2.1:g}n)/{width:.17g})-tanh((time-{base+6.1:g}n)/{width:.17g}))' for base in [0,10]]
    rows.append('BIN IN 0 V={'+'+'.join(wave)+'}')
    for prefix,count,key in [('C',15,'coarse'),('E',31,'fine')]:
        for bit in range(count):rows.append(f'V{prefix}{bit} {prefix}{bit} 0 '+str(1.8 if bit<spec[key] else 0))
    rows += ['XD '+' '.join('0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in circuit.PORTS)+' '+circuit.NAME,
             f'CLOAD OUT 0 {spec["load_ff"]}f','.tran 2p 20n 0 2p']
    probes={'IN','OUT','VDD',*[p for p in circuit.PORTS if p.startswith(('C','E'))]}
    probes.update(n for d in devices for n in d['terminals'] if n!='0')
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end',''])


def measure(folder,spec,devices):
    result=pulses.measure(folder,spec,devices)
    names,w=validate(folder/'bench.raw',set(),20e-9);idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']];stable=t>=1.5e-9;worst=0.
    for prefix,count,key in [('coarse',15,'coarse'),('fine',31,'fine')]:
        for bit in range(count):
            target=1.8 if bit<spec[key] else 0
            worst=max(worst,float(np.max(np.abs(w[stable,idx[f'v(xd.{prefix}{bit})']]-target))))
            if prefix=='fine':worst=max(worst,float(np.max(np.abs(w[stable,idx[f'v(xd.fine_b{bit})']]-(1.8-target)))))
    if worst>.18:raise ValueError('Mux-bank internal thermometer control violates logic margins')
    result.update(internal_control_max_deviation_v=worst,
        scope='Full sixteen-coarse/thirty-one-fine source return-mux bank with real forward/fine RC and two isolated pulses; no mux/turn/control/common-wire physical RC, dense ROM, updates, periodic clock, full-PVT or PHY admission')
    return result


def prepare(compound,fine):
    if engine()!='ngspice':raise ValueError('Explicitly select pinned ngspice')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    cells,bank,orders,devices,paths=libraries(compound,fine,sc)
    code=[Path(__file__),Path(circuit.__file__),Path(families.__file__),Path(families.compound.__file__),Path(parsing.__file__),Path(pulses.__file__),
          ROOT/'scripts/dcdl_mim_bank_physical_v2.py',ROOT/'scripts/dcdl_mim_bank_v2.py',ROOT/'scripts/mim_switch_2x3_v2.py',
          ROOT/'scripts/audit_passive_rc_v3.py',ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/lvs_utils.py',
          ROOT/'scripts/spice_library.py',ROOT/'scripts/reduce_rc.py',ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/run_native_binary_v2.py',
          ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_slots.py',ROOT/'scripts/spice_engine.py',
          ROOT/'scripts/run_ngspice.py',ROOT/'build/tools/ngspice.json',ROOT/'clocking_v2.json']
    models=[sc,pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity=dict(version=VERSION,compound=str(compound.relative_to(ROOT)),fine=str(fine.relative_to(ROOT)),source_library=str(sc),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code},pdk_files={str(p):sha(p) for p in models},
        simulator=provenance(),specs=specifications(),orders=orders,devices=devices)
    out=ROOT/'build/diagnostics/dcdl_mux_return_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'cells.spice',cells);write(out/'bank.spice',bank);tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics/dcdl_mux_return_v2' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or engine()!='ngspice' or provenance()!=i['simulator']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=len(i['specs'])):raise ValueError('Mux-bank pilot inputs changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:raise ValueError('Mux-bank task/deck changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior mux-bank campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='dcdl_mux_return_v2_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],m['identity']['devices'])
            except Exception as exception:error=str(exception)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='mux_bank_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path,nargs='?')
    p.add_argument('--compound',type=Path);p.add_argument('--fine',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.compound is None or a.fine is None:p.error('Provide both native RC proofs')
        print(prepare(a.compound.resolve(),a.fine.resolve()),flush=True)
    else:
        if a.artifact is None:p.error('Provide prepared campaign')
        run(a.artifact.resolve())
