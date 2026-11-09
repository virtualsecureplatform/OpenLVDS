# SPDX-License-Identifier: GPL-3.0-only
"""Static tagged-detector input contract with true 10-90% ramp times.

Four isolated decisions retain the legacy 10 ns tag cadence; this is not a
300 MHz periodic-clock or physical detector qualification.
"""
import itertools
import re
import numpy as np
import expand_phase_threshold_pvt_v2 as donor
import clocking_profile_300 as policy

VERSION='explicit-10-90-static-detector-inputs-300-v1'
PAIRS=((100,100),(20,20),(20,250),(250,20),(250,250))
KEYS={'process','temperature','drive','swap','offset_ps','reference_slew_ps','feedback_slew_ps','positive_offset','settle_ps'}


def specifications():
    r=policy.load()['requirements']
    return [dict(process=p,temperature=t,drive=1,swap=swap,offset_ps=o,
        reference_slew_ps=a,feedback_slew_ps=b,positive_offset=pos,settle_ps=20000)
        for p,t,(a,b),swap,o,pos in itertools.product(r['process_corners'],r['temperatures_c'],
            PAIRS,(0,1),(-20,0,20),(0,1))]


def check(s):
    r=policy.load()['requirements']
    if (set(s)!=KEYS or s['process'] not in r['process_corners'] or s['temperature'] not in r['temperatures_c']
            or s['drive']!=1 or s['swap'] not in (0,1) or s['offset_ps'] not in (-20,0,20)
            or (s['reference_slew_ps'],s['feedback_slew_ps']) not in PAIRS
            or s['positive_offset'] not in (0,1) or s['settle_ps']!=20000):
        raise ValueError('Undeclared detector source point')


def parameters(s,phase):
    check(s)
    if phase not in ('R','F'):raise ValueError('Unknown detector input')
    slew=s['reference_slew_ps' if phase=='R' else 'feedback_slew_ps']
    return s['settle_ps']+2100+(s['offset_ps'] if phase=='F' else 0),slew/.8


def points(s,phase):
    first,full=parameters(s,phase);rows=[(0.,0.)]
    for k in range(4):
        for center,rising in ((first+k*10000,True),(first+k*10000+1250,False)):
            rows += [(center+(f-.5)*full,1.8*(f if rising else 1-f)) for f in (0,.1,.5,.9,1)]
    rows.append((s['settle_ps']+42000,0.))
    if any(b[0]<=a[0] for a,b in zip(rows,rows[1:])):raise ValueError('Overlapping detector ramps')
    return rows


def evaluate(t,s,phase,independent=False):
    if not independent:
        rows=points(s,phase);return np.interp(t,[x for x,v in rows],[v for x,v in rows])
    first,full=parameters(s,phase);value=np.zeros_like(np.asarray(t),dtype=float)
    for k in range(4):
        up=np.clip(.5+(t-first-k*10000)/full,0,1)
        down=np.clip(.5-(t-first-k*10000-1250)/full,0,1)
        value+=1.8*np.minimum(up,down)
    return value


def fixture(out,s,devices):
    check(s);text=donor.fixture(out,s,devices)
    for instance,phase in (('VR','R'),('VF','F')):
        pattern=r'(?m)^'+instance+' '+phase+r' 0 PULSE\([^\n]+\)$'
        if len(re.findall(pattern,text))!=1:raise ValueError('Legacy detector source changed')
        block='\n'.join([instance+' '+phase+' 0 PWL(',
            *[f'+ {t:.17g}p {v:.17g}' for t,v in points(s,phase)],'+ )'])
        text=re.sub(pattern,lambda m:block,text,count=1)
    return text.replace(text.splitlines()[0],'OpenLVDS '+VERSION,1)
