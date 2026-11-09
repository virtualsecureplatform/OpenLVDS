# SPDX-License-Identifier: GPL-3.0-only
"""Full native source detector decisions, true input slew and MOS health.

Every source MOS terminal is measured; physical matching remains separate.
"""
import itertools
import numpy as np
import detector_inputs_300_v1 as waveform
from native_binary_raw_v2 import validate

VERSION='native-corrected-input-static-detector-measure-300-v1'
P5='sky130_fd_pr__pfet_g5v0d10v5'


def crossings(t,v,level,rising,independent=False):
    if not independent:
        selected=np.flatnonzero((v[:-1]<level)&(v[1:]>=level) if rising else (v[:-1]>level)&(v[1:]<=level))
        return t[selected]+(level-v[selected])*(t[selected+1]-t[selected])/(v[selected+1]-v[selected])
    # Separate bracket discovery and interpolation implementation.
    mask=np.diff((v>=level).astype(np.int8))
    selected=np.where(mask==(1 if rising else -1))[0]
    result=[]
    for i in selected:
        fraction=(level-float(v[i]))/float(v[i+1]-v[i])
        result.append((1-fraction)*float(t[i])+fraction*float(t[i+1]))
    return np.array(result)


def measure(folder,task,independent=False):
    s=task['spec'];waveform.check(s)
    def canonical(n):
        mapping={'REF':'R','FDB':'F','REF_FAST':'RFAST','FDB_FAST':'FFAST','VDDD':'VDD'}
        return 'v('+mapping.get(n,n).replace(':','.').lower()+')'
    fixed={'R','F','POS','SW','QA','QB','RFAST','FFAST','RTH','FTH','XD:ha','XD:hb','VDD','VDDIO','XF:VCM'}
    wanted={canonical(n) for n in fixed}
    wanted.update(canonical(n) for d in task['devices'] for n in d['terminals'] if n not in ('0','VSS'))
    names,w=validate(folder/'bench.raw',wanted,62000e-12);index={n:k for k,n in enumerate(names)}
    t=w[:,index['time']]*1e12
    if abs(t[0])>1e-6 or t[-1]>62000+1e-6 or np.max(np.diff(t))>1+1e-6:
        raise ValueError('Detector capture lacks DC, complete tail or 1 ps resolution')
    def get(n):return np.zeros(len(t)) if n in ('0','VSS') else w[:,index[canonical(n)]]
    def at(n,when):
        v=get(n)
        if not independent:return float(np.interp(when,t,v))
        k=int(np.searchsorted(t,when,side='right'))
        if k==0 or k==len(t):raise ValueError('Unbracketed detector observation')
        weight=(when-t[k-1])/(t[k]-t[k-1]);return float(v[k-1]*(1-weight)+v[k]*weight)
    inputs={}
    for phase in ('R','F'):
        first,full=waveform.parameters(s,phase);v=get(phase);edges={}
        for rising in (True,False):
            label='rise' if rising else 'fall'
            for fraction in (.1,.5,.9):
                a=crossings(t,v,1.8*fraction,rising,independent)
                expected=first+np.arange(4)*10000+(0 if rising else 1250)+(fraction-.5)*full*(1 if rising else -1)
                if len(a)!=4:raise ValueError('Missing/extra detector input event')
                edges[label+str(fraction)]=a
                if np.max(np.abs(a-expected))>.02:raise ValueError('Wrong detector input epoch, width or offset')
        error=float(np.max(np.abs(v-waveform.evaluate(t,s,phase,independent))))
        if error>1e-9:raise ValueError('Detector input differs from declared waveform')
        slew_error=max(
            float(np.max(np.abs((edges['rise0.9']-edges['rise0.1'])-.8*full))),
            float(np.max(np.abs((edges['fall0.1']-edges['fall0.9'])-.8*full))))
        if slew_error>1e-6:raise ValueError('Wrong true 10-90 detector input slew')
        inputs[phase]=dict(all_four_rises_and_falls_present=True,maximum_ideal_voltage_error_v=error,
            maximum_slew_error_ps=slew_error,measured_10_90_ps=.8*full)
    votes=[];conditioned=[];threshold=[];tags=True
    for i in range(4):
        start=s['settle_ps']+i*10000
        tags=bool(tags and min(at('XD:'+n,start+6000) for n in ('ha','hb'))>=1.62
                  and max(at('XD:'+n,start+9000) for n in ('ha','hb'))<=.18)
        a,b=at('QA',start+6000),at('QB',start+6000)
        if s['swap']:a,b=b,a
        state=lambda v:0 if v<=.18 else 1 if v>=1.62 else None
        pair=state(a),state(b);votes.append(1 if pair==(0,1) else -1 if pair==(1,0) else None)
        for first,second,end,collection in (('RFAST','FFAST',5000,conditioned),('RTH','FTH',6000,threshold)):
            edges=[]
            for n in (first,second):
                if independent:
                    left=np.searchsorted(t,start+1500);right=np.searchsorted(t,start+end)
                    a=crossings(t[left:right],get(n)[left:right],.9,True,True)
                else:
                    select=(t>=start+1500)&(t<start+end)
                    a=crossings(t[select],get(n)[select],.9,True)
                if len(a)!=1:raise ValueError('Missing/extra conditioned detector event')
                edges.append(float(a[0]))
            collection.append(edges[1]-edges[0])
    stress=[]
    for d in task['devices']:
        v=[get(n) for n in d['terminals']]
        limit=d.get('limit_v',5.5 if d['model']==P5 else 1.95)
        span=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(v,2)) if independent else float(np.max(np.ptp(np.stack(v),axis=0)))
        stress.append(dict(device=d['name'],max_terminal_difference_v=span,limit_v=limit,passed=span<=limit))
    ref=get('XF:VCM')[t>=s['settle_ps']]
    common=bool(np.max(np.abs(ref-.9))<=.01)
    fixed_supply=bool(np.max(np.abs(get('VDD')-1.8))<=1e-9 and np.max(np.abs(get('VDDIO')-3.3))<=1e-9)
    controls=bool(np.max(np.abs(get('POS')-1.8*s['positive_offset']))<=.01
                  and np.max(np.abs(get('SW')-1.8*s['swap']))<=.01)
    expected=(1 if s['offset_ps']>0 else -1) if s['offset_ps'] else (1 if s['positive_offset'] else -1)
    sign=all(v==expected for v in votes);stress_ok=all(d['passed'] for d in stress)
    passed=bool(tags and sign and stress_ok and common and fixed_supply and controls)
    return dict(version=VERSION,input=inputs,input_contract_passed=True,votes=votes,expected_vote=expected,
        all_four_decisions_passed=sign,tags_retained_and_cleared_passed=tags,
        conditioned_feedback_minus_reference_ps=conditioned,threshold_feedback_minus_reference_ps=threshold,
        native_stress=stress,native_stress_passed=stress_ok,
        common_mode_min_v=float(ref.min()),common_mode_max_v=float(ref.max()),common_mode_passed=common,
        fixed_supply_passed=fixed_supply,static_control_passed=controls,source_point_passed=passed,
        physical_detector_admitted=False,full_native_stress_qualified=False,qualified_phy=False,
        scope='Four isolated source decisions, explicit input contract and all-source-device health only; no physical matching, periodic clock or loaded DLL admission')
