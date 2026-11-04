#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate component-RC clock assembly and independently remeasure raw data."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_native_clock_components_v5 as pilot
from verify_conditioned_clock_v2 import regenerated_front,compare_result
from measure_conditioned_dcc_v2 import measure
from probe_digital_dcc_v2 import sha

ROOT=pilot.ROOT
VERSION='independent-approved-40-60-duty-native-clock-raw-verification-v2.4'


def regenerate(out):
    m=pilot.bound(out);i=m['identity'];jm=pilot.joint.bound(ROOT/i['parent'])
    front,base=regenerated_front(ROOT/jm['identity']['parent']);cells={}
    for name in i['components']:
        group,_=pilot.witnesses(ROOT/name)
        if set(group)&set(cells):raise ValueError('Duplicate native component')
        cells.update(group)
    modules=pilot.components.compose(cells);modules.update({n:front[n] for n in ['frontend.spice','bias.spice']})
    if set(modules)!=set(m['libraries']) or any((out/n).read_text()!=text for n,text in modules.items()):raise ValueError('Component clock library regeneration changed')
    devices={};c=pilot.components
    for v in ['p3_c1','p3_c3']:
        text='\n'.join(modules[n] for n in ['cells.spice','clean.spice','release.spice',v+'.spice'])
        ds=[d for d in base if d['name'].startswith(('XF:','XB:'))]
        ds+=c.mapped_mos(text,c.clean.NAME,dict(F0='F0',F180='F180',P0='P0',P180='P180',MON0='MON0',MON180='MON180',VPWR='VDD',VGND='0'),'XC')
        ds+=c.mapped_mos(text,c.dcc.NAME,dict(VGND='0',VPWR='VDD',clock_out='Q',phase0='P0',phase180='P180',reset_n='RESET_N'),'XD')
        for tag,clk,rst in [('XR0','P0','RESET_N'),('XR180','P180','RESET_180')]:
            ds+=c.mapped_mos(text,c.release.NAME,dict(CLK=clk,REQUEST='REQUEST',RESET_N=rst,VPWR='VDD',VGND='0'),tag)
        devices[v]=ds
    if devices!=i['devices']:raise ValueError('Native component MOS coverage changed')
    return m,devices


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m,devices=regenerate(out);state=json.loads((out/'state.json').read_text());summary=json.loads((out/'summary.json').read_text())
        if state['status']!='native_component_pilot_complete' or state['cases']!=len(m['tasks']) or state['errors'] or len(summary['rows'])!=len(m['tasks']):
            raise ValueError('Require complete numerical-error-free component pilot')
        files=[out/n for n in ['manifest.json','summary.json','state.json',*m['libraries']]];rows=[]
        for n,task in enumerate(m['tasks']):
            folder=out/str(n);retained=json.loads((folder/'summary.json').read_text());spec=task['spec'];ds=devices[spec['variant']]
            if retained!=summary['rows'][n] or retained['task']!=task or retained['error'] is not None:raise ValueError('Component task/aggregate mismatch')
            if (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,ds):raise ValueError('Component deck regeneration changed')
            for name in ['bench.cir','bench.raw']:
                if sha(folder/name)!=retained['files'][name]:raise ValueError('Component raw/deck witness changed')
            measured=measure(folder,spec,ds,'Independent component-RC waveform verification');compare_result(measured,retained['result'])
            rows.append(dict(id=task['id'],spec=spec,passed=measured['pilot_passed'],
                requirements={k:measured[k] for k in ['startup_passed','event_integrity_passed','reset_after_two_clock_edges_passed','common_mode_passed','half_cycle_passed','terminal_screen_passed']},
                mean_half_cycle_error_ps=measured['half_cycle_error_ps'],
                low_voltage_terminal_peak_v=max(d['max_terminal_difference_v'] for d in measured['terminal_stress'] if d['limit_v']==1.95),qualified_phy=False))
            files += [folder/n for n in ['summary.json','bench.cir','bench.raw']]
        pilot.bound(out);witnesses={str(p.relative_to(ROOT)):sha(p) for p in files}
        code=[Path(__file__),Path(pilot.__file__),Path(pilot.components.__file__),ROOT/'scripts/verify_conditioned_clock_v2.py',ROOT/'scripts/measure_conditioned_dcc_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),witnesses=witnesses,code={str(p.relative_to(ROOT)):sha(p) for p in code})
        receipt=ROOT/'build/diagnostics/native_clock_components_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        body=json.dumps(dict(identity=identity,rows=rows,passed=all(r['passed'] for r in rows),qualified_phy=False,
            scope='Regenerated native component RC assembly/decks/MOS coverage and independent raw remeasurement only; ideal inter-component wires, no whole-backend or full-PVT admission'),indent=2)+'\n'
        if any(sha(ROOT/n)!=h for n,h in witnesses.items()):raise ValueError('Component witness changed during verification')
        receipt.mkdir(parents=True,exist_ok=True);path=receipt/'summary.json'
        if path.exists() and path.read_text()!=body:raise ValueError('Retain prior component verification')
        if not path.exists():path.write_text(body)
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
