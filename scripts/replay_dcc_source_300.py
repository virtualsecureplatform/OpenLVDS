#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reproduce selected complete DCC source results and independently time events."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import dcc_source_300 as producer

ROOT=producer.ROOT
VERSION='independent-dcc-source-native-replay-300-v1'
sha=producer.sha
REQUIRED={'bench.cir','bench.ngspice.cir','bench.raw','bench.cir.prn','ngspice.log','console.log'}


def transitions(t,v):
    state=v>=.9;indices=np.flatnonzero(state[1:]!=state[:-1])
    times=t[indices]+(.9-v[indices])*(t[indices+1]-t[indices])/(v[indices+1]-v[indices])
    return times,state[indices+1]


def independent(names,w,spec):
    t=w[:,names.index('time')]*1e12
    stop=(2+1000/spec['mhz']*18)*1000
    if (not np.isfinite(w).all() or t[0]>1e-6 or t[-1]<stop-.01 or np.any(np.diff(t)<=0)):
        raise ValueError('Require complete finite native source transient')
    get=lambda n:w[:,names.index('v('+n+')')]
    edges=lambda n:transitions(t,get(n))
    rises=lambda n:edges(n)[0][edges(n)[1]]
    falls=lambda n:edges(n)[0][~edges(n)[1]]
    period=1e6/spec['mhz'];start,end=10000,40000
    input_checks=[]
    for node,duty in [('p0',spec['duty']),('p180',1-spec['duty'])]:
        rising=rises(node);falling=falls(node);cycles=[]
        for a,b in zip(rising[:-1],rising[1:]):
            if not start<=a<end:continue
            f=falling[(falling>a)&(falling<b)]
            cycles.append(dict(period_ps=float(b-a),duty=float((f[0]-a)/(b-a)) if len(f)==1 else None))
        ok=bool(len(cycles)>=7 and all(c['duty'] is not None and abs(c['period_ps']-period)<=.02
            and abs(c['duty']-duty)<=1e-5 for c in cycles))
        input_checks.append(dict(node=node,cycles=cycles,passed=ok))
    phase=[]
    a=rises('p0');b=rises('p180');spacing=period/2+spec['phase_error_ps']
    for at in a[(a>=start)&(a<end)]:
        after=b[b>at]
        phase.append(float(after[0]-at) if len(after) else None)
    phase_ok=bool(phase and all(v is not None and abs(v-spacing)<=.02 for v in phase))
    source=np.sort(np.r_[a,b]);event=rises('xd.events');q,levels=edges('q');events=[]
    for at,nxt in zip(source[:-1],source[1:]):
        if not start<=at<end:continue
        pulse=event[(event>at)&(event<nxt)];output=q[(q>at)&(q<nxt)]
        events.append(dict(source_ps=float(at),pulse_count=len(pulse),output_count=len(output),
            passed=bool(len(pulse)==len(output)==1)))
    hold=[]
    for clock,tag in [('p0','a'),('p180','b')]:
        rising=rises(clock);falling=falls(clock);pulse=rises('xd.'+tag);ending=falls('xd.'+tag)
        for at,nxt in zip(rising[:-1],rising[1:]):
            if not start<=at<end:continue
            p=pulse[(pulse>at)&(pulse<nxt)];f=ending[ending>p[0]] if len(p)==1 else []
            c=falling[falling>at];maximum=None;ok=False
            if len(f) and len(c):
                mask=(t>f[0]+20)&(t<c[0]-20)
                maximum=float(get('xd.'+tag+'reset')[mask].max()) if np.any(mask) else None
                ok=maximum is None or maximum<=.18
            hold.append(dict(channel=tag,source_ps=float(at),pulse_count=len(p),reset_max_v=maximum,passed=bool(len(p)==1 and ok)))
    half={True:[],False:[]};swing=[]
    for at,nxt,high in zip(q[:-1],q[1:],levels[:-1]):
        if not start<=at<end:continue
        half[bool(high)].append(float(nxt-at));segment=get('q')[(t>=at)&(t<=nxt)]
        swing.append(bool(len(segment) and (segment.max()>=1.62 if high else segment.min()<=.18)))
    error=max(abs(float(np.mean(v))-period/2) for v in half.values()) if all(half.values()) else None
    balanced=spec['phase_error_ps']==0
    passed=bool(all(c['passed'] for c in input_checks) and phase_ok and len(events)>16
        and all(e['passed'] for e in events) and hold and all(h['passed'] for h in hold)
        and swing and all(swing) and (not balanced or error is not None and error<=50))
    return dict(independent_source_screen_passed=passed,input_checks=input_checks,
        phase_spacing_passed=phase_ok,observed_phase_spacing_ps=phase,event_checks=events,
        reset_hold_checks=hold,full_swing_output_intervals=bool(swing and all(swing)),
        mean_half_cycle_error_ps=error,balanced_half_cycle_passed=bool(error is not None and error<=50) if balanced else None)


def replay(parent,ids,full=False):
    manifest=producer.bound(parent)
    if full:
        if ids:raise ValueError('Full replay selects the complete matrix itself')
        if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=810,errors=0,qualified_phy=False):
            raise ValueError('Require complete error-free source campaign for matrix admission')
        ids=[t['id'] for t in manifest['tasks']]
    if not ids or len(ids)!=len(set(ids)):raise ValueError('Require unique explicit completed case IDs')
    tasks={t['id']:t for t in manifest['tasks']};inputs={str(parent/'manifest.json'):sha(parent/'manifest.json')}
    inputs.update(manifest['identity']['inputs']);inputs.update(manifest['identity']['pdk_files'])
    for n in manifest['libraries']:inputs[str(parent/n)]=sha(parent/n)
    files=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    inputs.update({str(p):sha(p) for p in files});recorded=[]
    for case in ids:
        if case not in tasks:raise ValueError('Unknown source case '+case)
        folder=parent/case;path=folder/'summary.json';row=json.loads(path.read_text())
        if row['task']!=tasks[case] or row['error'] is not None or not REQUIRED<=set(row['files']):
            raise ValueError('Incomplete or mismatched source case '+case)
        for n,digest in row['files'].items():
            if Path(n).name!=n or sha(folder/n)!=digest:raise ValueError('Changed source witness '+n)
            inputs[str(folder/n)]=digest
        inputs[str(path)]=sha(path);recorded.append(row)
    if full:
        report=json.loads((parent/'summary.json').read_text())
        if report['rows']!=recorded or report['source_screen_passed']!=all(producer.passed(r['result'],r['task']['spec']) for r in recorded):
            raise ValueError('Source matrix aggregate differs from native case results')
        inputs.update({str(parent/n):sha(parent/n) for n in ['summary.json','state.json']})
    identity=dict(version=VERSION,inputs=inputs,parent=str(parent.relative_to(ROOT)),cases=ids,full_matrix=full)
    out=ROOT/'build/diagnostics/dcc_source_native_replay_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        rows=[]
        for row in recorded:
            spec=row['task']['spec'];folder=parent/row['task']['id']
            if producer.source.measure(folder,spec)!=row['result']:raise ValueError('Original source measurements do not reproduce')
            names,w=producer.source.base.read_raw(folder/'bench.raw')
            rows.append(dict(case=row['task']['id'],original_metrics_reproduced=True,
                original_source_passed=producer.passed(row['result'],spec),independent=independent(names,w,spec)))
        if any(sha(Path(n))!=h for n,h in inputs.items()):raise ValueError('Source replay inputs changed')
        producer.bound(parent)
        passed=all(r['original_source_passed'] and r['independent']['independent_source_screen_passed'] for r in rows)
        producer.atomic(out/'summary.json',dict(rows=rows,all_selected_source_screens_passed=passed,
            complete_810_source_matrix_admitted=bool(full and len(rows)==810 and passed),
            source_only=True,qualified_phy=False,scope=producer.SCOPE))
        producer.atomic(out/'state.json',dict(status='complete',cases=len(rows),qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path)
    p.add_argument('ids',nargs='*');p.add_argument('--full',action='store_true');a=p.parse_args()
    print(replay(a.artifact.resolve(),a.ids,a.full),flush=True)
