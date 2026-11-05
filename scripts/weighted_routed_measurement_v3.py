# SPDX-License-Identifier: GPL-3.0-only
"""Stream complete routed-bank measurements with built-in JSON scalar types.

The limits, pulse windows and reported schema match the retained v2 producer.
Row blocks avoid repeatedly paging a multi-gigabyte raw file for every MOS.
"""
import numpy as np
from native_binary_raw_v2 import read
from probe_digital_dcc_v2 import crossings

VERSION='streamed-full-routed-native-measurement-v3.1'
SCOPE='Complete routed 16-choice bank RC, SS40 sparse LSB/carry/repeat pulses only; no dense code, periodic-clock, full-PVT or PHY admission'


def measure(folder,spec,witness):
    names,w=read(folder/'bench.raw');idx={n:i for i,n in enumerate(names)};n=len(names)
    def column(node):
        if node=='0':return n
        key='v('+node.replace(':','.').lower()+')'
        if key not in idx:raise ValueError('Missing requested native vector '+key)
        return idx[key]
    devices=witness['devices'];groups=witness['controls']
    if not devices or len({d['name'] for d in devices})!=len(devices):raise ValueError('Missing/duplicate routed native device witness')
    if any(len(d['terminals'])!=4 or d['limit_v']!=1.95 for d in devices):raise ValueError('Native terminal coverage or voltage limit changed')
    mos=np.array([[column(node) for node in d['terminals']] for d in devices])
    ctrl=np.array([column(node) for c in groups for node in c['nodes']],dtype=int)
    if any(not c['nodes'] or c['kind'] not in ['coarse','fine','fine_b'] for c in groups):raise ValueError('Invalid native control observation group')
    edges=np.cumsum([0]+[len(c['nodes']) for c in groups]);t=np.asarray(w[:,idx['time']])*1e12
    stop=len(spec['codes'])*10000
    if (not np.isfinite(t).all() or t[0]!=0 or t[-1]<stop*(1-1e-8) or np.any(np.diff(t)<=0)):
        raise ValueError('Incomplete/nonmonotonic routed native transient')
    peaks=np.zeros(len(devices));errors=np.zeros((len(spec['codes']),len(groups)));seen=np.zeros(len(spec['codes']),dtype=bool)
    targets=np.empty_like(errors)
    for slot,code in enumerate(spec['codes']):
        for j,c in enumerate(groups):
            target=1.8 if (c['bit']<spec['coarse'] if c['kind']=='coarse' else ((code>>c['bit'])&1)) else 0.
            targets[slot,j]=1.8-target if c['kind']=='fine_b' else target
    for start in range(0,len(w),128):
        block=w[start:start+128]
        if not np.isfinite(block).all():raise ValueError('Nonfinite routed native transient')
        values=np.take(block,np.minimum(mos,n-1),axis=1);values[:,mos==n]=0
        peaks=np.maximum(peaks,np.max(np.ptp(values,axis=2),axis=0))
        values=np.take(block,np.minimum(ctrl,n-1),axis=1);values[:,ctrl==n]=0
        bt=t[start:start+128]
        for slot in range(len(spec['codes'])):
            stable=(bt>=slot*10000+1500)&(bt<slot*10000+9500)
            if not np.any(stable):continue
            seen[slot]=True
            for j in range(len(groups)):
                worst=float(np.max(np.abs(values[stable,edges[j]:edges[j+1]]-targets[slot,j])))
                errors[slot,j]=max(errors[slot,j],worst)
    if not seen.all():raise ValueError('Missing full stable control window')
    # These twenty-two adjacent public probe columns are small copies. All
    # wide/native terminal and control scans above are bounded row operations.
    observed=['IN','OUT',*[f'C{i}' for i in range(15)],*[f'B{i}' for i in range(5)]]
    thin={node:np.array(w[:,column(node)]) for node in observed}
    samples=[];controls=[]
    for slot,code in enumerate(spec['codes']):
        base=slot*10000;window=(t>=base)&(t<=base+10000);stable=(t>=base+1500)&(t<base+9500)
        sample=dict(code=code,pulse_integrity_passed=True)
        for up,label in [(True,'rise'),(False,'fall')]:
            a=crossings(t[window],thin['IN'][window],up);b=crossings(t[window],thin['OUT'][window],up)
            valid=bool(len(a)==1 and len(b)==1 and b[0]>a[0])
            sample[label+'_delay_ps']=float(b[0]-a[0]) if valid else None
            sample['pulse_integrity_passed']=bool(sample['pulse_integrity_passed'] and valid)
        samples.append(sample)
        for bit in range(20):
            pin=f'C{bit}' if bit<15 else f'B{bit-15}'
            target=(1.8 if bit<spec['coarse'] else 0.) if bit<15 else (1.8 if (code>>(bit-15))&1 else 0.)
            if np.max(np.abs(thin[pin][stable]-target))>.01:raise ValueError('Routed bank external control stimulus changed')
        for j,c in enumerate(groups):
            worst=float(errors[slot,j]);controls.append(dict(code=code,kind=c['kind'],bit=c['bit'],observed_nodes=len(c['nodes']),maximum_deviation_v=worst,passed=bool(worst<=.18)))
    stress=[dict(device=d['name'],max_terminal_difference_v=float(peak),limit_v=1.95,passed=bool(peak<=1.95)) for d,peak in zip(devices,peaks)]
    pulse_ok=all(s['pulse_integrity_passed'] for s in samples);control_ok=all(c['passed'] for c in controls);voltage_ok=all(d['passed'] for d in stress)
    headroom=1e6/410/4-max(s[e+'_delay_ps'] for s in samples if s['code']==0 for e in ['rise','fall']) if spec['coarse']==0 and pulse_ok else None
    return dict(samples=samples,controls=controls,terminal_stress=stress,pulse_integrity_passed=pulse_ok,
        routed_control_settling_passed=control_ok,terminal_screen_passed=voltage_ok,minimum_quarter_headroom_ps=headroom,
        component_pilot_passed=bool(pulse_ok and control_ok and voltage_ok),qualified_phy=False,legal_code_table_admitted=False,scope=SCOPE)
