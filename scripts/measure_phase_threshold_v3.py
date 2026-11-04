# SPDX-License-Identifier: GPL-3.0-only
"""Time-origin-aware native threshold measurements; no waveform time shifting."""
import itertools
import math
import numpy as np
import probe_digital_dcc_v2 as base

P5='sky130_fd_pr__pfet_g5v0d10v5'


def measure(folder,task):
    spec=task['spec'];settle=spec['settle_ps']
    if not math.isfinite(settle) or settle<0:raise ValueError('Invalid quiescent prefix')
    names,w=base.read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
    if not np.isfinite(w).all() or t[-1]<settle+42000-.01:raise ValueError('Incomplete threshold trace')
    def get(n):
        mapping={'REF':'R','FDB':'F','REF_FAST':'RFAST','FDB_FAST':'FFAST','VDDD':'VDD'}
        return np.zeros(len(t)) if n in ['0','VSS'] else w[:,names.index('v('+mapping.get(n,n).replace(':','.').lower()+')')]
    if np.max(np.abs(get('POS')-1.8*spec['positive_offset']))>.01:raise ValueError('Unstable threshold control')
    votes=[];voltages=[];conditioned=[];threshold=[]
    for i in range(4):
        start=settle+i*10000;when=start+6000
        if min(float(np.interp(when,t,get('XD:'+n))) for n in ['ha','hb'])<1.62:
            raise ValueError('Missing retained conditioned tag')
        if any(np.interp(start+9000,t,get('XD:'+n))>.18 for n in ['ha','hb']):
            raise ValueError('Conditioned tags did not clear')
        a=float(np.interp(when,t,get('QA')));b=float(np.interp(when,t,get('QB')))
        if spec['swap']:a,b=b,a
        voltages.append([a,b]);state=lambda v:0 if v<=.18 else (1 if v>=1.62 else None)
        pair=state(a),state(b);votes.append(1 if pair==(0,1) else (-1 if pair==(1,0) else (None if None in pair else 0)))
        for first,second,end,collection in [('RFAST','FFAST',5000,conditioned),('RTH','FTH',6000,threshold)]:
            select=(t>=start+1500)&(t<start+end)
            a=base.crossings(t[select],get(first)[select]);b=base.crossings(t[select],get(second)[select])
            if len(a)!=1 or len(b)!=1:raise ValueError('Missing/extra conditioned or threshold edge')
            collection.append(float(b[0]-a[0]))
    stress=[]
    for device in task['devices']:
        v=[get(n) for n in device['terminals']]
        maximum=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(v,2))
        limit=5.5 if device['model']==P5 else 1.95
        stress.append(dict(device=device['name'],max_terminal_difference_v=maximum,limit_v=limit,passed=maximum<=limit))
    ref=get('XF:VCM')[t>=settle]
    expected=(1 if spec['offset_ps']>0 else -1) if spec['offset_ps'] else (1 if spec['positive_offset'] else -1)
    return dict(votes=votes,settled_output_voltages_v=voltages,conditioned_feedback_minus_reference_ps=conditioned,
        threshold_feedback_minus_reference_ps=threshold,threshold_increment_ps=[a-b for a,b in zip(threshold,conditioned)],
        frontend_stress=stress,frontend_stress_passed=all(d['passed'] for d in stress),
        common_mode_min_v=float(ref.min()),common_mode_max_v=float(ref.max()),common_mode_passed=bool(np.max(np.abs(ref-.9))<=.01),
        correct_sign_fraction=sum(v==expected for v in votes)/len(votes),expected_vote=expected,positive_offset=spec['positive_offset'],
        settle_ps=settle,qualified_phy=False,detector_admitted=False,
        scope='Native threshold data with explicit time origin; no physical or DLL admission')
