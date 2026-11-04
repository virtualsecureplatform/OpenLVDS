#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate native clock libraries/decks and remeasure completed raw cohorts."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_continuous_clock_conditioner_v2 as front
import probe_conditioned_dcc_v3 as joint
from measure_conditioned_dcc_v2 import measure
from verify_dcc_static_pilots_v4 import same
from probe_digital_dcc_v2 import sha

ROOT=front.ROOT
VERSION='independent-conditioned-clock-native-source-verification-v2.1'


def regenerated_front(out):
    """Rebuild MOS coverage from native generators, independently of saved lists."""
    m=front.bound(out);i=m['identity'];parent=ROOT/i['parent'];fm=front.dcc.bound(parent)
    library=Path(fm['identity']['pdk']).read_text();original,ds=front.frontend.circuit('tail140_w20')
    analog=ROOT/i['frontend']
    sources={'frontend.spice':original.replace('w=22 l=22','w=30 l=30'),
        'bias.spice':(analog/'bias.spice').read_text(),'clean.spice':front.clean.source(library),
        'dcc.spice':front.dcc.circuit.source('tg1',library)[0]}
    if set(sources)!=set(m['libraries']):raise ValueError('Unexpected front-end library set')
    if any((out/n).read_text()!=text for n,text in sources.items()):raise ValueError('Native front-end regeneration changed')
    mapping=dict(REF='R0',FDB='R180',REF_FAST='F0',FDB_FAST='F180',VDDD='VDD',VDDIO='VDDIO',PB='PB')
    devices=[dict(name=d['name'],model=d['model'],limit_v=5.5 if d['model']=='sky130_fd_pr__pfet_g5v0d10v5' else 1.95,
        terminals=[mapping.get(n,n) for n in d['terminals']]) for d in ds]
    devices+=front.clean.mapped_mos(sources['bias.spice'],dict(IREF='PB',NB='NB',VDDIO='VDDIO',VSS='0'),'XB')
    devices+=front.clean.mapped_mos(sources['clean.spice'],dict(F0='F0',F180='F180',P0='P0',P180='P180',MON0='MON0',MON180='MON180',VPWR='VDD',VGND='0'),'XC')
    devices+=front.clean.mapped_mos(sources['dcc.spice'],dict(VGND='0',VPWR='VDD',clock_out='QD',phase0='P0',phase180='P180',reset_n='0'),'XD')
    if devices!=i['devices']:raise ValueError('Front-end terminal coverage changed')
    return sources,devices


def regenerated_joint(out):
    m=joint.bound(out);i=m['identity'];parent=ROOT/i['parent'];sources,base=regenerated_front(parent)
    rm=joint.sizing.bound(ROOT/i['ratios']);library=Path(rm['identity']['pdk']).read_text()
    sources={n:text for n,text in sources.items() if n!='dcc.spice'}
    sources['release.spice']=joint.release.source(library);devices={}
    for v in ['p3','p4']:
        text=joint.sizing.circuit.source(v,library)[0];sources[v+'.spice']=text
        ds=[d for d in base if not d['name'].startswith('XD:')]
        ds+=front.clean.mapped_mos(text,dict(VGND='0',VPWR='VDD',clock_out='Q',phase0='P0',phase180='P180',reset_n='RESET_N'),'XD')
        for inst,clk,rst in [('XR0','P0','RESET_N'),('XR180','P180','RESET_180')]:
            ds+=front.clean.mapped_mos(sources['release.spice'],dict(CLK=clk,REQUEST='REQUEST',RESET_N=rst,VPWR='VDD',VGND='0'),inst)
        devices[v]=ds
    if set(sources)!=set(m['libraries']) or any((out/n).read_text()!=text for n,text in sources.items()):
        raise ValueError('Native joint-source regeneration changed')
    if devices!=i['devices']:raise ValueError('Joint terminal coverage changed')
    return sources,devices


def compare_result(actual,retained):
    # Scope describes which actor performed the same analysis; all measurements
    # and pass/fail gates must match, including every individual MOS screen.
    a={k:v for k,v in actual.items() if k!='scope'};b={k:v for k,v in retained.items() if k!='scope'}
    if not same(a,b):raise ValueError('Raw remeasurement disagrees with retained result')


def verify(out):
    if out.parent.name=='continuous_clock_conditioner_v2':producer=front;regenerate=regenerated_front;status='continuous_conditioner_pilot_complete'
    elif out.parent.name=='conditioned_dcc_v2':producer=joint;regenerate=regenerated_joint;status='joint_source_pilot_complete'
    else:raise ValueError('Unknown conditioned clock context')
    if out.parent.parent!=ROOT/'build/diagnostics':raise ValueError('Unexpected artifact root')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=producer.bound(out);i=m['identity'];state=json.loads((out/'state.json').read_text())
        if state['status']!=status or state['cases']!=len(m['tasks']) or state['errors']:
            raise ValueError('Require complete numerical-error-free cohort')
        sources,devices=regenerate(out);summary=json.loads((out/'summary.json').read_text())
        if len(summary['rows'])!=len(m['tasks']):raise ValueError('Incomplete aggregate')
        files=[out/n for n in ['manifest.json','summary.json','state.json',*sources]];rows=[]
        for n,task in enumerate(m['tasks']):
            folder=out/str(n);row=json.loads((folder/'summary.json').read_text());spec=task['spec']
            if row!=summary['rows'][n] or row['task']!=task or row['error'] is not None:raise ValueError('Task/aggregate mismatch')
            ds=devices if producer is front else devices[spec['variant']]
            if (folder/'bench.cir').read_text()!=producer.fixture(out,spec,ds):raise ValueError('Deck regeneration changed')
            for name in ['bench.cir','bench.raw']:
                if sha(folder/name)!=row['files'][name]:raise ValueError('Changed raw/deck witness')
            result=front.measure(folder,task,ds) if producer is front else measure(folder,spec,ds,'Independent raw remeasurement')
            compare_result(result,row['result']);files += [folder/n for n in ['summary.json','bench.cir','bench.raw']]
            rows.append(dict(id=task['id'],spec=spec,passed=result['clock_conditioning_feasibility_passed' if producer is front else 'pilot_passed'],
                timing_error_ps=result['maximum_half_spacing_error_ps' if producer is front else 'half_cycle_error_ps'],
                low_voltage_terminal_peak_v=max(d['max_terminal_difference_v'] for d in result['terminal_stress'] if d['limit_v']==1.95),qualified_phy=False))
        producer.bound(out);witnesses={str(p.relative_to(ROOT)):sha(p) for p in files}
        code=[Path(__file__),ROOT/'scripts/verify_dcc_static_pilots_v4.py',ROOT/'scripts/measure_conditioned_dcc_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),witnesses=witnesses,code={str(p.relative_to(ROOT)):sha(p) for p in code})
        receipt=ROOT/'build/diagnostics/conditioned_clock_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        body=json.dumps(dict(identity=identity,rows=rows,cases=len(rows),passed=all(r['passed'] for r in rows),qualified_phy=False,
            scope='Exact native source/deck regeneration, independent MOS coverage reconstruction and raw remeasurement; bounded source pilot only, no full-PVT or physical clock admission'),indent=2)+'\n'
        if any(sha(ROOT/n)!=h for n,h in witnesses.items()):raise ValueError('Witness changed during verification')
        receipt.mkdir(parents=True,exist_ok=True);path=receipt/'summary.json'
        if path.exists() and path.read_text()!=body:raise ValueError('Retain prior receipt')
        if not path.exists():path.write_text(body)
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
