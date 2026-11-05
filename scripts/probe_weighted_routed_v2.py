#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Sparse native timing experiment using the complete verified routed-bank RC.

Execution requires the matched physical fine-control settling receipt. Preserve
all sixteen coarse choices, all inserted devices and every distributed rail.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import itertools
import numpy as np
import weighted_routed_observation_v2 as observation
import weighted_bank_control_gate_v3 as control_gate
import probe_weighted_direct_v4 as baseline
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_library import checked_netlist
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=baseline.ROOT
VERSION='whole-routed-repaired-weighted-bank-sparse-native-timing-v2.1'
CONTEXT='weighted_routed_v2'
CODES=[0,1,15,16,31,0]


def specifications():return baseline.specifications()


def receipt_bound(receipt):
    # The scientific venv supplies NumPy; the tools Python supplies KLayout.
    code='import sys,json; from pathlib import Path; sys.path.insert(0,"scripts"); import verify_weighted_bank_rc_v2 as v; p=Path(sys.argv[1]); m=v.bound(p); print(json.dumps(m))'
    p=subprocess.run(['python3','-c',code,str(receipt)],cwd=ROOT,capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


def libraries(receipt):
    rm=receipt_bound(receipt);report=json.loads((receipt/'summary.json').read_text());info=report['extraction']
    text=checked_netlist(info);raw_folder=(ROOT/info['raw_netlist']).parent
    ext=raw_folder/'openlvds_weighted_bank_physical_v2_rcx.ext'
    witness=observation.observations(text,ext.read_text(),'openlvds_weighted_bank_physical_v2')
    extraction=ROOT/rm['identity']['parent'];em=json.loads((extraction/'manifest.json').read_text())['identity']
    physical=json.loads((ROOT/em['parent']/'manifest.json').read_text())['identity']
    routed=json.loads((ROOT/physical['parent']/'manifest.json').read_text())['identity']
    frame=json.loads((ROOT/routed['access_view']/'manifest.json').read_text())['identity']
    network=json.loads((ROOT/frame['network']/'manifest.json').read_text())['identity']
    candidate=ROOT/network['parent'];cm=baseline.bound(candidate)['identity']
    if witness['ports']!=info['ports'] or sum(witness['primitive_counts'].values())!=report['proof']['native_primitives']:
        raise ValueError('Routed timing observations omit native devices or public terminals')
    inputs=[ext,ROOT/info['raw_netlist'],ROOT/info['netlist'],receipt/'manifest.json',receipt/'summary.json',receipt/'state.json',
            candidate/'manifest.json',extraction/'manifest.json',extraction/'summary.json']
    inputs += [ROOT/n for n in rm['identity']['inputs']]
    components={k:cm[k] for k in ['clock','fine_cells','repair']}
    return text,witness,components,inputs


def fixture(out,spec,witness):
    if spec['codes']!=CODES:raise ValueError('Routed timing code sequence changed')
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    rows=['OpenLVDS '+VERSION,f'.lib "{model}" {spec["process"]}',f'.include "{out}/bank.spice"',
          f'.options device temp={spec["temperature"]}',
          '.options timeint method=gear reltol=1e-4 abstol=1e-12','.options itl4=100','VDD VDD 0 1.8']
    width=spec['input_slew_ps']/1e12/(2*np.arctanh(.8))
    pulses=[f'0.9*(tanh((time-{10*i+2.1:g}n)/{width:.17g})-tanh((time-{10*i+6.1:g}n)/{width:.17g}))' for i in range(len(CODES))]
    rows.append('BIN IN 0 V={'+'+'.join(pulses)+'}')
    for bit in range(15):rows.append(f'VC{bit} C{bit} 0 '+str(1.8 if bit<spec['coarse'] else 0))
    for bit in range(5):
        values=[1.8 if (code>>bit)&1 else 0 for code in CODES];points=[f'0 {values[0]}'];half=spec['control_slew_ps']/2000
        for i in range(1,len(values)):points += [f'{10*i-half:g}n {values[i-1]}',f'{10*i+half:g}n {values[i]}']
        rows.append(f'VB{bit} B{bit} 0 PWL('+' '.join(points)+')')
    pins=['0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in witness['ports']]
    rows += ['XD '+' '.join(pins)+' openlvds_weighted_bank_physical_v2',f'CLOAD OUT 0 {spec["load_ff"]}f',
             f'.tran 2p {10*len(CODES)}n 0 2p']
    probes={'IN','OUT','VDD',*[f'B{i}' for i in range(5)],*[f'C{i}' for i in range(15)]}
    probes.update(n for d in witness['devices'] for n in d['terminals'] if n!='0')
    probes.update(n for c in witness['controls'] for n in c['nodes'] if n!='0')
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end',''])


def measure(folder,spec,witness):
    observed={'IN','OUT',*[f'C{i}' for i in range(15)],*[f'B{i}' for i in range(5)]}
    observed.update(n for d in witness['devices'] for n in d['terminals'] if n!='0')
    observed.update(n for c in witness['controls'] for n in c['nodes'] if n!='0')
    names,w=validate(folder/'bench.raw',{'v('+n.replace(':','.').lower()+')' for n in observed},len(CODES)*10e-9)
    idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12;zeros=np.zeros(len(t))
    def get(n):return zeros if n=='0' else w[:,idx['v('+n.replace(':','.').lower()+')']]
    samples=[];controls=[]
    for i,code in enumerate(CODES):
        base=i*10000;window=(t>=base)&(t<=base+10000);stable=(t>=base+1500)&(t<base+9500)
        sample=dict(code=code,pulse_integrity_passed=True)
        for up,label in [(True,'rise'),(False,'fall')]:
            a=crossings(t[window],get('IN')[window],up);b=crossings(t[window],get('OUT')[window],up)
            valid=len(a)==1 and len(b)==1 and b[0]>a[0]
            sample[label+'_delay_ps']=float(b[0]-a[0]) if valid else None
            sample['pulse_integrity_passed'] &= valid
        samples.append(sample)
        for bit in range(20):
            pin=f'C{bit}' if bit<15 else f'B{bit-15}'
            target=(1.8 if bit<spec['coarse'] else 0) if bit<15 else (1.8 if (code>>(bit-15))&1 else 0)
            if np.max(np.abs(get(pin)[stable]-target))>.01:raise ValueError('Routed bank external control stimulus changed')
        for c in witness['controls']:
            bit=c['bit'];target=1.8 if bit<spec['coarse'] else 0
            if c['kind']!='coarse':target=1.8 if ((code>>bit)&1) else 0
            if c['kind']=='fine_b':target=1.8-target
            worst=max(float(np.max(np.abs(get(n)[stable]-target))) for n in c['nodes'])
            controls.append(dict(code=code,kind=c['kind'],bit=bit,observed_nodes=len(c['nodes']),maximum_deviation_v=worst,passed=worst<=.18))
    stress=[]
    for d in witness['devices']:
        values=[get(n) for n in d['terminals']]
        peak=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2))
        stress.append(dict(device=d['name'],max_terminal_difference_v=peak,limit_v=1.95,passed=peak<=1.95))
    pulse_ok=all(s['pulse_integrity_passed'] for s in samples);control_ok=all(c['passed'] for c in controls);voltage_ok=all(d['passed'] for d in stress)
    headroom=1e6/410/4-max(s[e+'_delay_ps'] for s in samples if s['code']==0 for e in ['rise','fall']) if spec['coarse']==0 and pulse_ok else None
    return dict(samples=samples,controls=controls,terminal_stress=stress,pulse_integrity_passed=pulse_ok,
        routed_control_settling_passed=control_ok,terminal_screen_passed=voltage_ok,minimum_quarter_headroom_ps=headroom,
        component_pilot_passed=pulse_ok and control_ok and voltage_ok,qualified_phy=False,legal_code_table_admitted=False,
        scope='Complete routed 16-choice bank RC, SS40 sparse LSB/carry/repeat pulses only; no dense code, periodic-clock, full-PVT or PHY admission')


def prepare(receipt):
    if engine()!='ngspice':raise ValueError('Select the pinned ngspice engine')
    text,witness,components,paths=libraries(receipt)
    code=[Path(__file__),Path(observation.__file__),Path(baseline.__file__),Path(control_gate.__file__),
          ROOT/'scripts/verify_weighted_bank_rc_v2.py',ROOT/'scripts/native_binary_raw_v2.py',
          ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
          ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_library.py',ROOT/'clocking_v2.json']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    models=[pdk/'libs.tech/ngspice/sky130.lib.spice']+sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))
    identity=dict(version=VERSION,receipt=str(receipt.relative_to(ROOT)),components=components,specs=specifications(),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code},pdk_files={str(p):sha(p) for p in models},
        simulator=provenance(),witness=witness,maximum_step_ps=2,itl4=100,
        execution_prerequisite='independent-physical-fine-control-v4-repaired-bit4-guarded-both-biases')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'bank.spice',text);tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,witness))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={'bank.spice':sha(out/'bank.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or i['specs']!=specifications()
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=len(i['specs'])):
        raise ValueError('Routed-bank timing context changed')
    for n,task in enumerate(m['tasks']):
        if (task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']
            or (out/str(n)/'bench.cir').read_text()!=fixture(out,task['spec'],i['witness'])):
            raise ValueError('Routed-bank timing task or native observation deck changed')
    return m


def run(out,control_receipt):
    m=bound(out);i=m['identity'];c=i['components']
    proof=control_gate.require(control_receipt,ROOT/c['clock'],ROOT/c['fine_cells'],ROOT/c['repair'])
    receipt_bound(ROOT/i['receipt'])
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior routed-bank experiment')
        atomic(out/'control_gate.json',proof);atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);receipt_bound(ROOT/i['receipt'])
                    if control_gate.require(control_receipt,ROOT/c['clock'],ROOT/c['fine_cells'],ROOT/c['repair'])!=proof:
                        raise ValueError('Matched physical fine-control prerequisite changed')
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],i['witness'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='weighted_routed_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--control-receipt',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:
        if a.control_receipt is None:p.error('Provide the matched passing physical fine-control receipt')
        run(a.artifact.resolve(),a.control_receipt.resolve())
