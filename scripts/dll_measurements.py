# SPDX-License-Identifier: GPL-3.0-only
"""Named-vector measurements for isolated DLL architecture experiments."""
from pathlib import Path
import numpy as np
from verify_phase_detector import metrics as phase_metrics

def read_wave(path):
    with Path(path).open() as f:header=f.readline().split()
    wave=np.loadtxt(path,skiprows=1)
    if wave.ndim!=2 or wave.shape[1]!=len(header) or len(wave)<2 or not np.isfinite(wave).all() or not np.all(np.diff(wave[:,1])>0):
        raise ValueError('Incomplete or malformed waveform')
    return wave,{name.upper():i for i,name in enumerate(header)}

def column(w,h,name):return w[:,h['V('+name.upper()+')']]

def average(t,v):
    if len(t)<2 or t[-1]<=t[0]:raise ValueError('Empty measurement window')
    return float(np.sum((v[:-1]+v[1:])*.5*np.diff(t))/(t[-1]-t[0]))

def edges(t,v,level=.9,rising=True):
    high=v>=level;i=np.flatnonzero((~high[:-1]&high[1:]) if rising else (high[:-1]&~high[1:]))
    return t[i]+(level-v[i])*(t[i+1]-t[i])/(v[i+1]-v[i])

def complete(w,stop_ns):return bool(w[0,1]<=1e-15 and w[-1,1]>=stop_ns*1e-9-1e-12)

def phase(w,h,offset,start_ns=120,stop_ns=160):
    names=['REF','FDB','UP','DN','BAD']
    ref,fb,up,dn,bad=[column(w,h,n) for n in names]
    uf,df=[column(w,h,n) for n in ['UF','DF']]
    exported=np.column_stack([w[:,0],w[:,1],ref,fb,up,dn,uf-df,bad])
    result=phase_metrics(exported,offset,start_ns*1e-9,stop_ns*1e-9)
    keep=(w[:,1]>=start_ns*1e-9)&(w[:,1]<=stop_ns*1e-9);t=w[keep,1]
    result.update(complete=complete(w,stop_ns),uf_mean_v=average(t,uf[keep]),df_mean_v=average(t,df[keep]),
                  raw_area_difference_v=average(t,(up-dn)[keep]),filtered_area_difference_v=average(t,(uf-df)[keep]))
    result['passed']=bool(result['passed'] and result['complete'])
    return result

def logic(w,h,expected,start_ns=120,stop_ns=160):
    keep=(w[:,1]>=start_ns*1e-9)&(w[:,1]<=stop_ns*1e-9);bad=column(w,h,'BAD')[keep]
    ok=complete(w,stop_ns) and len(bad)>2 and (np.min(bad)>1.44 if expected else np.max(bad)<.36)
    return dict(passed=bool(ok),complete=complete(w,stop_ns),bad_min_v=float(bad.min()),bad_max_v=float(bad.max()),expected_bad=expected)

def loop(w,h,mhz,architecture,start_ns=1200,stop_ns=1500):
    t=w[:,1];period=1e-6/mhz
    ref=edges(t,column(w,h,'PH0'));quarter=edges(t,column(w,h,'PH90'))
    pdref=edges(t,column(w,h,'PD_REF'));fb=edges(t,column(w,h,'PH180'))
    within=lambda x:x[(x>(start_ns*1e-9+period))&(x<(stop_ns*1e-9-2*period))]
    phases=[];errors=[]
    for at in within(ref):
        after=quarter[quarter>at]
        if len(after):phases.append((after[0]-at)*1e12)
    for at in within(pdref):
        if len(fb):errors.append(float(np.min(abs(fb-at)))*1e12)
    if not phases or not errors:return dict(passed=False,complete=complete(w,stop_ns),cadence_passed=False,error='Missing quarter-phase or feedback clock')
    keep=(t>=start_ns*1e-9)&(t<=stop_ns*1e-9);time=t[keep]
    ctrl=column(w,h,'CTRL')[keep];bad=column(w,h,'BAD')[keep]
    qerror=max((abs(p-period*250e9) for p in phases),default=float('inf'))
    # Require complete cadence instead of allowing one surviving edge to pass.
    cadence=all(len(within(x))>=int((stop_ns-start_ns)*1e-9/period)-5 and
        np.max(abs(np.diff(within(x))-period))<.02*period for x in [ref,quarter,pdref,fb])
    result=dict(complete=complete(w,stop_ns),cadence_passed=bool(cadence),
        feedback_error_max_ps=max(errors,default=float('inf')),quarter_phase_error_max_ps=qerror,
        quarter_phase_min_ps=min(phases,default=None),quarter_phase_max_ps=max(phases,default=None),
        control_mean_v=average(time,ctrl),control_ripple_pp_mv=float(np.ptp(ctrl)*1000),
        phase_bad_max_v=float(bad.max()),loop_architecture=architecture)
    health=bool(np.all(ctrl>=0) and np.all(ctrl<=1.95))
    if architecture=='charge_pump':
        copy=column(w,h,'COPY')[keep];error=ctrl-copy
        result.update(control_copy_error_max_mv=float(np.max(abs(error))*1000),control_copy_mean_error_mv=average(time,error)*1000)
        health=health and result['control_copy_error_max_mv']<50
    else:
        result.update(control_copy_error_max_mv=None,copy_error_applicability='No replica buffer in this topology')
        health=health and result['control_ripple_pp_mv']<20
    result['passed']=bool(result['complete'] and cadence and health and phases and errors and qerror<100 and max(errors)<100 and bad.max()<.36)
    for n in ['UF','DF']:
        result[n.lower()+'_mean_v']=average(time,column(w,h,n)[keep])
    return result
