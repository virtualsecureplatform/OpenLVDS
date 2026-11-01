#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Instrument bounded source architectures with ideal current meters and terminal probes."""
import argparse
from contextlib import contextmanager
import itertools
from pathlib import Path
import re
import numpy as np
import receiver_architecture_experiment as experiment
from receiver_architectures import transform,VARIANTS
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
TOP=experiment.TOP
BASE_MEASURED=experiment.measured
BASE_REBIND=experiment.rebind
THIN_GUARD_V=1.95  # Existing project screen, not a foundry absolute rating.
METERS={'XCT':('CT','TAIL'),'XNCB':('NBC','REPLICA')}


def instrument(source,variant):
    source=transform(source,variant);block=text_block(source,TOP)
    if 'OBS_' in block:raise ValueError('Source already contains observation meters')
    for device,(drain,label) in METERS.items():
        pattern=r'(?m)^'+device+r'[ \t]+'+drain+r'(?=[ \t])'
        block,count=re.subn(pattern,device+' OBS_'+label+'_D',block)
        if count!=1:raise ValueError('Unexpected current-meter device '+device)
        # Zero volts preserves the original terminal potential. A 1 ohm
        # transresistance exports signed branch amperes as observable volts.
        lines=f'VOBS_{label} {drain} OBS_{label}_D 0\nHOBS_{label} OBS_I{label} VSS VOBS_{label} 1\n'
        block=block.replace('.ends '+TOP,lines+'.ends '+TOP)
    return replace(source,TOP,block)


def observe_deck(deck,parent,root):
    deck=BASE_REBIND(deck,parent,root)
    matches=list(re.finditer(r'(?im)^\.print tran[^\n]*$',deck))
    if len(matches)!=1 or any('HOBS_'+n in deck for n in ['IO','DIG']):raise ValueError('Unexpected observation fixture')
    for name,rail,value in [('VIO','VDDIO','3.3'),('VDIG','VDDD','1.8')]:
        if len(re.findall(r'(?m)^'+name+' '+rail+' 0 '+re.escape(value)+r'\s*$',deck))!=1:
            raise ValueError('Expected original fixed voltage source '+name)
    probes=['XR:XCORE:'+n for n in ['OBS_ITAIL','OBS_IREPLICA','OBS_TAIL_D','OBS_REPLICA_D',
        'RESTORE0','RESTORE1']]+['IREF','VDDIO','VDDD','OBS_IIO','OBS_IDIG']
    at=matches[0].end();deck=deck[:at]+' '+ ' '.join('V('+n+')' for n in probes)+deck[at:]
    # These outputs draw no current from the measured supply branches.
    deck,count=re.subn(r'(?im)^\.end\s*$', 'HOBS_IO OBS_IIO 0 VIO 1\nHOBS_DIG OBS_IDIG 0 VDIG 1\n.end',deck)
    if count!=1:raise ValueError('Expected one fixture end')
    return deck


def observations(wave,headers,rows):
    BASE_MEASURED(wave,headers,True)  # Full finite monotonic original 144 ns trace.
    t=wave[:,1];times=(np.arange(12)*12+10)*1e-9
    def voltage(node):
        if node=='VSS':return np.zeros(len(wave))
        key='V('+({'PB':'IREF','VDDIO':'VDDIO','VDDD':'VDDD'}.get(node,'XR:XCORE:'+node)).upper()+')'
        if key not in headers:raise ValueError('Missing architecture observation '+key)
        return wave[:,headers[key]]
    current={}
    for _,(node,label) in METERS.items():
        if np.max(abs(voltage(node)-voltage('OBS_'+label+'_D')))>1e-8:
            raise ValueError('Current meter changed a terminal potential')
        amps=voltage('OBS_I'+label)
        current[label.lower()]=dict(signed_samples_a=np.interp(times,t,amps).tolist(),
            min_signed_a=float(amps.min()),max_signed_a=float(amps.max()),
            absolute_samples_a=np.interp(times,t,abs(amps)).tolist())
    devices={}
    for name in ['XCT','XC0','XC1','XCD','XCM','XNCB']:
        _,nodes,model,params=rows[name];values=[voltage(n) for n in nodes]
        peaks=[]
        for a,b in itertools.combinations(range(4),2):
            delta=abs(values[a]-values[b]);i=int(np.argmax(delta))
            peaks.append(dict(pair=['DGSB'[a],'DGSB'[b]],voltage_v=float(delta[i]),time_ns=float(t[i]*1e9)))
        thin=bool(re.fullmatch(r'sky130_fd_pr__(?:n|p)fet_01v8(?:_lvt)?',model))
        peak=max(peaks,key=lambda p:p['voltage_v'])
        devices[name]=dict(model=model,nodes=nodes,params=params,maximum_terminal_difference=peak,
            thin_guard_applies=thin,thin_guard_passed=peak['voltage_v']<=THIN_GUARD_V if thin else None,
            settled_vds_samples_v=np.interp(times,t,values[0]-values[2]).tolist())
    supply={}
    for label,rail in [('IO',3.3),('DIG',1.8)]:
        key='V(OBS_I'+label+')'
        if key not in headers:raise ValueError('Missing supply-current meter '+key)
        amps=wave[:,headers[key]]
        supply[label.lower()]=dict(signed_source_current_samples_a=np.interp(times,t,amps).tolist(),
            delivered_power_samples_w=(-rail*np.interp(times,t,amps)).tolist())
    return dict(sample_times_ns=(times*1e9).tolist(),currents=current,devices=devices,
        fixture_supply_measurements=supply,thin_guard_v=THIN_GUARD_V,
        observed_thin_guard_passed=all(d['thin_guard_passed'] for d in devices.values() if d['thin_guard_applies']),
        scope='Six source decision/bias devices only. Signed meter amperes equal output volts / 1 ohm. Power covers the complete original fixture on each fixed rail, not isolated receiver power. No BSIM VDSAT, region, remaining-device stress, dynamic or native qualification.')


@contextmanager
def profile(variant,analyzing=False):
    if variant not in VARIANTS:raise ValueError('Unknown receiver architecture')
    previous=(experiment.transform,experiment.rebind,experiment.measured,experiment.CODE)
    try:
        experiment.transform=instrument;experiment.rebind=observe_deck
        experiment.CODE=sorted(set(experiment.CODE)|{NAME})
        if analyzing:
            plain=transform(experiment.source_variant((ROOT/'analog/openlvds.spice').read_text(),False),variant)
            rows={r[0]:r for r in circuits(plain)[TOP][1]}
            def measured(wave,headers,headroom=True):
                return dict(BASE_MEASURED(wave,headers,headroom),observations=observations(wave,headers,rows))
            experiment.measured=measured
        yield
    finally:experiment.transform,experiment.rebind,experiment.measured,experiment.CODE=previous


def prepare(parent,variant):
    with profile(variant):return experiment.prepare(parent,variant)


def run(root,wait_slot=None):
    import json
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest['identity']['code'].get(NAME)!=experiment.digest(Path(__file__)):
        raise ValueError('Architecture observation producer changed')
    with profile(manifest['identity']['architecture_variant'],True):return experiment.run(root,wait_slot)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--variant',choices=VARIANTS);p.add_argument('--wait-slot',type=int,choices=range(6));a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve(),a.variant),flush=True)
    else:run(a.artifact.resolve(),a.wait_slot)
