#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Snapshot a native DLL trace and diagnose G/Y without qualifying the circuit."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

import numpy as np
from dll_campaign import atomic
from dll_measurements import average,edges
from dll_stability import margins
from measure_dll_stability import instrument_source
from native_ac import run as ac_run,read_complex
from qualify_dll_candidate import validate,evaluate
from spice_engine import engine,provenance

ROOT=Path(__file__).resolve().parents[1]
CONTROL_LIMIT_MV=20.


def sha(data):return hashlib.sha256(data).hexdigest()


def raw_prefix(data):
    start=data.index(b'Binary:\n')+8;header=data[:start].decode()
    if 'complex' in header:raise ValueError('Expected real transient data')
    n=int(re.search(r'No\. Variables:\s*(\d+)',header)[1])
    count=int(re.search(r'No\. Points:\s*(\d+)',header)[1])
    names=[x.lower() for x in re.findall(r'^\s*\d+\s+(\S+)\s+\S+\s*$',header,re.M)]
    if n<2 or len(names)!=n or 'time' not in names:raise ValueError('Invalid native trace columns')
    rows=(len(data)-start)//(8*n);trailing=(len(data)-start)%(8*n)
    if len(names)!=n or rows<2:raise ValueError('Missing native trace rows')
    wave=np.frombuffer(data[start:start+rows*8*n],dtype='<f8').reshape(rows,n)
    if not np.isfinite(wave).all() or np.any(np.diff(wave[:,names.index('time')])<=0):raise ValueError('Invalid native trace rows')
    return names,wave,dict(header_points=count,complete_rows=rows,trailing_bytes_ignored=trailing,raw_finalized=count==rows and trailing==0)


def interval(t,v,start,end):
    if start<t[0] or end>t[-1] or end<=start:raise ValueError('Observation interval unavailable')
    keep=(t>start)&(t<end);x=np.r_[start,t[keep],end];y=np.r_[np.interp(start,t,v),v[keep],np.interp(end,t,v)]
    return dict(mean_v=average(x,y),min_v=float(y.min()),max_v=float(y.max()),range_mv=float(np.ptp(y)*1000))


def analyze(names,wave,task):
    t=wave[:,names.index('time')];spec=task['spec']
    def v(alias):return wave[:,names.index('v('+task['aliases'][alias].replace(':','.').lower()+')')]
    start=spec['start_ns']*1e-9;end=min(spec['end_ns']*1e-9,float(t[-1]))
    if end-start<25e-9:raise ValueError('Need at least ten scoring-window cycles for diagnosis')
    control=interval(t,v('CTRL'),start,end)
    dc_start=max(start,end-50e-9);dc={n:interval(t,v(n),dc_start,end)['mean_v'] for n in ['CTRL','UP','DN']}
    refs=edges(t,v('PH0'));pd=edges(t,v('PD_REF'));feedback=edges(t,v('PH180'));cycles=[]
    for a,b in zip(refs[:-1],refs[1:]):
        if a<start or b>end or abs(b-a-2.5e-9)>50e-12:continue
        fb=feedback[(feedback>a)&(feedback<b)]
        if len(fb)!=1 or not len(pd):continue
        ref=pd[np.argmin(abs(pd-fb[0]))];ctrl=interval(t,v('CTRL'),a,b)
        cycles.append(dict(time_ns=float((a+b)*.5e9),control_mean_v=ctrl['mean_v'],
            control_range_mv=ctrl['range_mv'],signed_feedback_error_ps=float((fb[0]-ref)*1e12)))
    if len(cycles)<8:raise ValueError('Insufficient native clock cycles for diagnosis')
    x=np.array([c['control_mean_v'] for c in cycles]);y=np.array([c['signed_feedback_error_ps'] for c in cycles])*1e-12
    xx=x-x.mean();yy=y-y.mean();den=float(xx@xx);slope=float(xx@yy/den) if den>1e-20 else None
    residual=yy-slope*xx if slope is not None else yy
    r2=float(1-residual@residual/(yy@yy)) if yy@yy>1e-30 else None
    fit=dict(inferred_delay_gain_s_per_v=slope,r_squared=r2,control_span_mv=float(np.ptp(x)*1000),
        usable=bool(slope is not None and slope<0 and r2 is not None and r2>=.8 and np.ptp(x)>=.001),
        limitation='Inferred from closed-loop trajectory; not an independent forced-control measurement')
    return dict(qualified_phy=False,qualification_verdict=None,scoring_interval_ns=[start*1e9,end*1e9],
        original_scoring_interval_ns=[spec['start_ns'],spec['end_ns']],control=control,
        control_limit_mv=CONTROL_LIMIT_MV,observed_control_limit_exceeded=control['range_mv']>=CONTROL_LIMIT_MV,
        cycle_mean_range_mv=float(np.ptp(x)*1000),cycle_ripple_max_mv=max(c['control_range_mv'] for c in cycles),
        dc_averaging_interval_ns=[dc_start*1e9,end*1e9],operating_point=dc,delay_gain_fit=fit,cycles=cycles)


def code(parent):
    names=set(parent['identity']['code'])|{'diagnose_native_dll_loop.py','measure_dll_stability.py','native_ac.py','dll_stability.py'}
    return {n:sha((ROOT/'scripts'/n).read_bytes()) for n in sorted(names)}


def prepare(qualification,case,allow_partial=False):
    qualification=qualification.resolve()
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):raise ValueError('Use a native qualification artifact')
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice environment')
    parent=json.loads((qualification/'manifest.json').read_text());validate(qualification,parent)
    if not parent['identity']['variant'].startswith('ota_'):raise ValueError('Expected an OTA loop')
    task=next(t for t in parent['tasks'] if t['id']==case)
    if task['fast_rc'] or task['spec']['kind']!='loop' or task['spec'].get('mhz')!=400 or task['spec'].get('duty')!=.5:
        raise ValueError('Use a native nominal loop case')
    raw=(qualification/case/'bench.raw').read_bytes();names,wave,description=raw_prefix(raw)
    complete=description['raw_finalized'] and wave[-1,names.index('time')]>=task['spec']['stop_ns']*1e-9-1e-12
    if not complete and not allow_partial:raise ValueError('Transient incomplete; explicitly select --allow-partial for engineering diagnosis')
    analysis=analyze(names,wave,task);process=task['spec']['process'];temp=task['spec']['temperature']
    gains=[];sources={}
    for offset in [-50,50]:
        name=f'phase_{process}_{temp}_{offset}ps';pt=next(t for t in parent['tasks'] if t['id']==name)
        folder=qualification/name;report=json.loads((folder/'summary.json').read_text());metrics=evaluate(qualification,pt)
        if not report['passed'] or not metrics['passed'] or metrics!=report['metrics'] or sha((folder/'bench.cir.prn').read_bytes())!=report['waveform_sha256']:
            raise ValueError('Native detector gain proof changed')
        gains.append(metrics['raw_area_difference_v'])
        for leaf in ['summary.json','bench.cir.prn']:sources[str((folder/leaf).relative_to(ROOT))]=sha((folder/leaf).read_bytes())
    kpd=(gains[1]-gains[0])/100e-12
    if kpd<=0:raise ValueError('Unexpected native PFD gain sign')
    captured=dict(qualification=str(qualification.relative_to(ROOT)),qualification_manifest_sha256=sha((qualification/'manifest.json').read_bytes()),
        task=task,raw_snapshot_sha256=sha(raw),source_reports=sources,code=code(parent),simulator_provenance=provenance(),allow_partial=allow_partial)
    root=ROOT/'build/diagnostics/dll_loop_diagnosis'/sha(json.dumps(captured,sort_keys=True).encode())[:16]
    root.mkdir(parents=True,exist_ok=True)
    if (root/'manifest.json').exists():return root
    (root/'trace_snapshot.raw').write_bytes(raw);(root/'qualification_manifest.json').write_bytes((qualification/'manifest.json').read_bytes())
    library=(qualification/'full.spice').read_text();(root/'library.spice').write_text(library)
    instrument=instrument_source(library,parent['identity']['full_models']['observation_nodes']['CTRL'][0]);(root/'instrument.spice').write_text(instrument)
    for name in captured['code']:(root/name).write_bytes((ROOT/'scripts'/name).read_bytes())
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice';dc=analysis['operating_point'];tasks=[]
    for clock in [0,1.8]:
        for mode in ['g','y']:
            label=f'ac_{clock:g}_{mode}';folder=root/label;folder.mkdir()
            text=(f'Native DLL diagnostic only {case} {label}\n.lib "{pdk}" {process}\n.include "{root}/instrument.spice"\n'
                f'.temp {temp}\n.options klu method=gear reltol=1e-4 abstol=1e-12\nVA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n'
                'XB PB NB VDDIO 0 lvds_bias\nXA CLK VDDD PH0 PH90 PH180 PH270 FB PD_REF BAD UP DN PB VDDIO VDDD 0 CTRL openlvds_dll_analog\n'
                'C0 PH0 0 40f\nC90 PH90 0 40f\nC180 PH180 0 20f\nC270 PH270 0 20f\nCF FB 0 20f\n'
                f'VCLK CLK 0 {clock:g}\nVU UP 0 DC {dc["UP"]:.17g} AC {0.5 if mode=="g" else 0}\n'
                f'VN DN 0 DC {dc["DN"]:.17g} AC {0.5 if mode=="g" else 0} 180\n'
                f'VCTRL CTRL 0 DC {dc["CTRL"]:.17g} AC {1 if mode=="y" else 0}\n.ac dec 40 10k 1G\n.save i(VCTRL)\n.end\n')
            (folder/'bench.cir').write_text(text);tasks.append(dict(id=label,clock_v=clock,mode=mode,deck_sha256=sha(text.encode())))
    validate(qualification,parent)
    manifest=dict(identity=captured,raw_description=description,transient_complete=bool(complete),qualified_phy=False,
        analysis=analysis,kpd_v_per_s=kpd,tasks=tasks,library_sha256=sha((root/'library.spice').read_bytes()),instrument_sha256=sha((root/'instrument.spice').read_bytes()))
    atomic(root/'manifest.json',manifest);return root


def run(root):
    root=root.resolve()
    if not root.is_relative_to(ROOT/'build/diagnostics/dll_loop_diagnosis'):raise ValueError('Use a captured diagnostic artifact')
    manifest=json.loads((root/'manifest.json').read_text());captured=manifest['identity'];qualification=ROOT/captured['qualification']
    def unchanged():
        parent=json.loads((qualification/'manifest.json').read_text());validate(qualification,parent)
        if code(parent)!=captured['code'] or sha((qualification/'manifest.json').read_bytes())!=captured['qualification_manifest_sha256'] or provenance()!=captured['simulator_provenance']:
            raise ValueError('Diagnostic native context changed')
        for leaf,key in [('trace_snapshot.raw','raw_snapshot_sha256')]:
            if sha((root/leaf).read_bytes())!=captured[key]:raise ValueError('Diagnostic snapshot changed')
        for leaf,key in [('library.spice','library_sha256'),('instrument.spice','instrument_sha256')]:
            if sha((root/leaf).read_bytes())!=manifest[key]:raise ValueError('Diagnostic library changed')
        if any(sha((ROOT/p).read_bytes())!=value for p,value in captured['source_reports'].items()):raise ValueError('Detector gain proof changed')
        if any(sha((root/n).read_bytes())!=value for n,value in captured['code'].items()):raise ValueError('Captured diagnostic code changed')
    unchanged();responses={}
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for task in manifest['tasks']:
            unchanged();deck=root/task['id']/'bench.cir'
            if sha(deck.read_bytes())!=task['deck_sha256']:raise ValueError('Diagnostic AC fixture changed')
            previous=deck.with_suffix('.evidence.json')
            if previous.exists():
                evidence=json.loads(previous.read_text());raw=deck.with_suffix('.raw')
                if (evidence['deck_sha256']!=task['deck_sha256'] or evidence['raw_sha256']!=sha(raw.read_bytes()) or
                    evidence['simulator_provenance']!=provenance() or evidence['producer_sha256']!=captured['code']['native_ac.py']):raise ValueError('Diagnostic AC evidence changed')
            else:raw=ac_run(deck)
            names,wave=read_complex(raw);frequency=wave[:,names.index('frequency')].real
            responses[(task['clock_v'],task['mode'])]=wave[:,names.index('i(vctrl)')]
        unchanged();fit=manifest['analysis']['delay_gain_fit'];models=[]
        if fit['usable']:
            groups=[(responses[(c,'g')],-responses[(c,'y')]) for c in [0,1.8]]
            groups.append((groups[0][0]+groups[1][0],groups[0][1]+groups[1][1]))
            for numerator,denominator in groups:
                result=margins(frequency,numerator/denominator,manifest['kpd_v_per_s'],fit['inferred_delay_gain_s_per_v'],400e6)
                models.append({k:v for k,v in result.items() if k!='loop'})
        atomic(root/'summary.json',dict(diagnostic_complete=True,qualified_phy=False,qualification_verdict=None,
            scope='Engineering AC diagnostic with trajectory-inferred delay gain; no native-step validation or qualification',
            manifest_sha256=sha((root/'manifest.json').read_bytes()),analysis=manifest['analysis'],models=models,
            files={str(p.relative_to(root)):sha(p.read_bytes()) for p in root.glob('ac_*/*') if p.is_file()}))
    print(root/'summary.json',flush=True);return 0


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('qualification',type=Path);a.add_argument('case');a.add_argument('--allow-partial',action='store_true')
    a=s.add_parser('run');a.add_argument('artifact',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(a.qualification,a.case,a.allow_partial),flush=True);return 0
    return run(a.artifact)


if __name__=='__main__':raise SystemExit(main())
