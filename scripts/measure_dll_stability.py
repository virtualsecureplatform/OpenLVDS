#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure native extracted DLL return gain and validate its averaged step model."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import numpy as np
from dll_campaign import atomic,closure,text_block
from dll_measurements import read_wave,column,average,edges
from dll_stability import margins,predicted_step
from native_ac import run as ac_run,read_complex
from qualify_dll_candidate import loop_fixture,validate
from spice_engine import command,provenance
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def pulse_train(stop,step=None):
    at=5.;points=[(0,0)]
    while at<stop:
        period=1000/step if step and at>=1700-1e-6 else 2.5
        if step or abs(at-80)>1e-6:
            points.extend([(at-.05,0),(at+.05,1.8),(at+period/2-.05,1.8),(at+period/2+.05,0)])
        at+=period
    return 'VCLK CLK 0 PWL('+' '.join(f'{t:.12g}n {v:g}' for t,v in points)+')\n'


def transient(out,text):
    out.mkdir(parents=True,exist_ok=True);deck=out/'bench.cir'
    previous=out/'evidence.json'
    if previous.exists():
        record=json.loads(previous.read_text())
        if record['deck_sha256']==hashlib.sha256(text.encode()).hexdigest() and record['waveform_sha256']==sha(out/'bench.cir.prn'):
            return read_wave(out/'bench.cir.prn')
        raise ValueError('Changed stability transient evidence')
    deck.write_text(text)
    with slot():
        result=subprocess.run(command(out/'ngspice.log',deck),cwd=out,capture_output=True,text=True)
    (out/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
    wave,header=read_wave(out/'bench.cir.prn')
    atomic(previous,dict(deck_sha256=sha(deck),waveform_sha256=sha(out/'bench.cir.prn'),simulator_provenance=provenance()))
    return wave,header


def erased_edge(wave,header,name):
    at=edges(wave[:,1],column(wave,header,name));width=np.diff(at)
    found=np.flatnonzero((at[:-1]>73e-9)&(at[:-1]<90e-9)&(width>4.25e-9)&(width<5.5e-9))
    if len(found)!=1:raise ValueError('Unwrapped delay marker missing on '+name)
    return at[found[0]]+2.5e-9


def settling_time(times,values,final):
    if abs(final)<1e-5:raise ValueError('Step is too small for model validation')
    tail=np.maximum.accumulate(abs(values-final)[::-1])[::-1]
    valid=np.flatnonzero(tail<=abs(final)*.1)
    if not len(valid):raise ValueError('Step did not settle within the observed interval')
    return float(times[valid[0]])


def measure_corner(qualification,manifest,root,process,temp):
    name=f'{process}_{temp}';out=root/name;out.mkdir(parents=True,exist_ok=True)
    task=next(t for t in manifest['tasks'] if t['id']==f'loop_{name}')
    summary=json.loads((qualification/task['id']/'summary.json').read_text())
    if not summary.get('passed'):raise ValueError('Native operating-point case did not pass: '+name)
    wave,header=read_wave(qualification/task['id']/'bench.cir.prn')
    if sha(qualification/task['id']/'bench.cir.prn')!=summary['waveform_sha256']:raise ValueError('Native waveform changed')
    for alias,node in task['aliases'].items():header['V('+alias.upper()+')']=header['V('+node.upper()+')']
    keep=(wave[:,1]>=1400e-9)&(wave[:,1]<=1500e-9)
    dc={n:average(wave[keep,1],column(wave,header,n)[keep]) for n in ['CTRL','UP','DN']}
    fields=manifest['identity']['full_models'];anchor=fields['observation_nodes']['CTRL'][0]
    library=(qualification/'full.spice').read_text()
    instrument=closure(library,['openlvds_dll_analog','lvds_bias'])
    match=re.search(r'(?im)^\.subckt openlvds_dll_analog[^\n]*(?:\n\+[^\n]*)*',instrument)
    instrument=instrument[:match.end()]+' '+anchor+instrument[match.end():]
    (out/'instrument.spice').write_text(instrument)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    def prefix(lib):
        return (f'Native extracted OTA stability {name}\n.lib "{pdk}" {process}\n.include "{lib}"\n'
                f'.temp {temp}\n.options klu method=gear reltol=1e-4 abstol=1e-12\n'
                'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n')
    common=('XB PB NB VDDIO 0 lvds_bias\n'
            'XA CLK VDDD PH0 PH90 PH180 PH270 FB PD_REF BAD UP DN PB VDDIO VDDD 0 CTRL openlvds_dll_analog\n'
            'C0 PH0 0 40f\nC90 PH90 0 40f\nC180 PH180 0 20f\nC270 PH270 0 20f\nCF FB 0 20f\n')
    delay=[]
    for index,offset in enumerate([-.01,0,.01]):
        body=(prefix(out/'instrument.spice')+common+f'VU UP 0 {dc["UP"]:.17g}\nVN DN 0 {dc["DN"]:.17g}\n'
              f'VCTRL CTRL 0 {dc["CTRL"]+offset:.17g}\n'+pulse_train(100)+
              '.tran 5p 100n 0 20p\n.print tran V(PH0) V(PH180) V(PD_REF)\n.end\n')
        w,h=transient(out/f'delay_{index}',body)
        if w[-1,1]<100e-9-1e-12:raise ValueError('Incomplete forced-control delay trace')
        delay.append(float(erased_edge(w,h,'PH180')-erased_edge(w,h,'PD_REF')))
    kdelay=(delay[2]-delay[0])/.02
    if kdelay>=0:raise ValueError('Unexpected delay-control polarity')
    gains=[]
    source_reports=[qualification/task['id']/'summary.json',qualification/task['id']/'bench.cir.prn']
    for offset in [-50,50]:
        path=qualification/f'phase_{name}_{offset}ps/summary.json';report=json.loads(path.read_text())
        if not report['passed']:raise ValueError('PFD characterization case failed')
        if sha(path.parent/'bench.cir.prn')!=report['waveform_sha256']:raise ValueError('PFD waveform changed')
        source_reports.extend([path,path.parent/'bench.cir.prn'])
        gains.append(report['metrics']['raw_area_difference_v'])
    kpd=(gains[1]-gains[0])/100e-12
    transfers=[];models=[]
    for clock in [0,1.8]:
        responses=[]
        for mode in ['g','y']:
            case=out/f'ac_{clock:g}_{mode}';case.mkdir(exist_ok=True)
            text=(prefix(out/'instrument.spice')+common+f'VCLK CLK 0 {clock:g}\n'
                  f'VU UP 0 DC {dc["UP"]:.17g} AC {0.5 if mode=="g" else 0}\n'
                  f'VN DN 0 DC {dc["DN"]:.17g} AC {0.5 if mode=="g" else 0} 180\n'
                  f'VCTRL CTRL 0 DC {dc["CTRL"]:.17g} AC {1 if mode=="y" else 0}\n'
                  '.ac dec 40 10k 1G\n.save i(VCTRL)\n.end\n')
            deck=case/'bench.cir';deck.write_text(text);names,raw=read_complex(ac_run(deck))
            frequency=raw[:,names.index('frequency')].real;responses.append(raw[:,names.index('i(vctrl)')])
        transfers.append((responses[0],-responses[1]))
        model=margins(frequency,responses[0]/(-responses[1]),kpd,kdelay,400e6)
        models.append({k:v for k,v in model.items() if k!='loop'})
    transfer=(transfers[0][0]+transfers[1][0])/(transfers[0][1]+transfers[1][1])
    model=margins(frequency,transfer,kpd,kdelay,400e6)
    models.append({k:v for k,v in model.items() if k!='loop'})
    validation=[]
    for target in [390,410]:
        spec=dict(kind='loop',process=process,temperature=temp,mhz=400,duty=.5,step_mhz=target,architecture='averaged_pfd_ota')
        body,probes,_,_=loop_fixture(spec,fields['observation_nodes'])
        body=re.sub(r'(?m)^VCLK[^\n]*\n',lambda _:pulse_train(3300,target),body)
        text=prefix(qualification/'full.spice')+body+'.tran 5p 3300n 0 20p\n.print tran '+' '.join('V('+n+')' for n in probes.values())+'\n.end\n'
        w,h=transient(out/f'step_{target}',text)
        if w[-1,1]<3300e-9-1e-12:raise ValueError('Incomplete step validation')
        ctrl=column(w,h,probes['CTRL']);t=w[:,1]
        initial=average(t[(t>=1630e-9)&(t<1690e-9)],ctrl[(t>=1630e-9)&(t<1690e-9)])
        sample=np.arange(2.5,1101,2.5)*1e-9
        observed=np.array([np.mean(np.interp(1700e-9+at+np.linspace(-1.25,1.25,101)*1e-9,t,ctrl))-initial for at in sample])
        pt,pv=predicted_step(frequency,model['loop'],kdelay,.5*(1e-6/target-2.5e-9))
        predicted=np.interp(sample,pt,pv);final=float(np.mean(observed[-10:]));pred_final=float(np.mean(predicted[-10:]))
        measured_t90=settling_time(sample,observed,final);predicted_t90=settling_time(sample,predicted,pred_final)
        amplitude_error=abs(pred_final/final-1);settling_error=abs(predicted_t90/measured_t90-1)
        validation.append(dict(target_mhz=target,amplitude_relative_error=float(amplitude_error),
            settling_relative_error=float(settling_error),measured_t90_ns=measured_t90*1e9,
            predicted_t90_ns=predicted_t90*1e9,passed=bool(amplitude_error<=.25 and settling_error<=.25)))
    result=dict(corner=name,passed=all(m['passed'] for m in models) and all(v['passed'] for v in validation),
        operating_point=dc,kpd_v_per_s=kpd,kdelay_s_per_v=kdelay,models=models,transient_validation=validation,
        source_reports={str(p.relative_to(qualification)):sha(p) for p in source_reports},
        files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='summary.json'})
    atomic(out/'summary.json',result);print(name,result['passed'],flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('qualification',type=Path);parser.add_argument('--all-pvt',action='store_true');a=parser.parse_args()
    qualification=a.qualification.resolve();manifest=json.loads((qualification/'manifest.json').read_text())
    validate(qualification,manifest)
    if not json.loads((qualification/'screen_summary.json').read_text())['passed']:raise ValueError('Native screening must pass first')
    corners=[('ss',0),('tt',25),('ff',0)]
    if a.all_pvt:
        req=json.loads((qualification/'requirements.json').read_text());corners=[(p,t) for p in req['process_corners'] for t in req['temperatures_c']]
    code={p.name:sha(p) for p in [Path(__file__),ROOT/'scripts/dll_stability.py',ROOT/'scripts/native_ac.py',
        ROOT/'scripts/spice_slots.py',ROOT/'scripts/qualify_dll_candidate.py',ROOT/'scripts/dll_measurements.py']}
    identity=dict(code=code,full_inputs=manifest['identity']['full_models']['inputs'],
        library_sha256=sha(qualification/'full.spice'),qualification_manifest_sha256=sha(qualification/'manifest.json'),
        simulator_provenance=provenance(),corners=corners)
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root=qualification/('stability_all_pvt' if a.all_pvt else 'stability_screen')/fingerprint;root.mkdir(parents=True,exist_ok=True)
    atomic(root/'manifest.json',identity)
    def safe_measure(pt):
        try:return measure_corner(qualification,manifest,root,*pt)
        except Exception as error:
            result=dict(corner=f'{pt[0]}_{pt[1]}',passed=False,error=str(error))
            folder=root/result['corner'];folder.mkdir(exist_ok=True);atomic(folder/'summary.json',result)
            print(result,flush=True);return result
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(safe_measure,corners))
    validate(qualification,manifest)
    phase=[m['phase_margin_min_deg'] for r in results for m in r.get('models',[]) if m.get('phase_margin_min_deg') is not None]
    gain=[m['gain_margin_min_db'] for r in results for m in r.get('models',[]) if m.get('gain_margin_min_db') is not None]
    report=dict(passed=all(r['passed'] for r in results),full_inputs=manifest['identity']['full_models']['inputs'],
        phase_margin_min_deg=min(phase) if phase else None,gain_margin_min_db=min(gain) if gain else None,
        simulator_provenance=provenance(),producer_sha256=sha(Path(__file__)),manifest_sha256=sha(root/'manifest.json'),all_pvt=a.all_pvt,results=results)
    atomic(root/'summary.json',report);print(root/'summary.json',flush=True)


if __name__=='__main__':main()
