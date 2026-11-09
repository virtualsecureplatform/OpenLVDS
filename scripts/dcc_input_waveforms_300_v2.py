#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Finite independent DCC clocks with explicit 10-90% slew and 50% epochs.

Fixture construction only: no simulation, source admission or PHY result.
"""
import itertools
import re
import clocking_profile_300 as policy
import dcc_source_300 as previous

VERSION='independent-duty-explicit-10-90-dcc-inputs-300-v2'
KEYS={'process','temperature','mhz','r_duty','f_duty','r_slew_10_90_ps','f_slew_10_90_ps','phase_error_ps','cycles'}


def specifications():
    r=policy.load()['requirements']
    return [dict(process=p,temperature=t,mhz=f,r_duty=a,f_duty=b,
                 r_slew_10_90_ps=x,f_slew_10_90_ps=y,phase_error_ps=e,cycles=18)
        for p,t,f,a,b,x,y,e in itertools.product(
            ['sf','ss','ff','fs','tt'],[40,0,25],r['clock_test_mhz'][::-1],
            [.6,.4,.5],[.6,.4,.5],[250,20],[250,20],[0,-140,140])]


def check(s):
    r=policy.load()['requirements']
    if (set(s)!=KEYS or s['process'] not in r['process_corners'] or s['temperature'] not in r['temperatures_c']
            or s['mhz'] not in r['clock_test_mhz'] or s['r_duty'] not in r['clock_duty'] or s['f_duty'] not in r['clock_duty']
            or s['r_slew_10_90_ps'] not in (20,250) or s['f_slew_10_90_ps'] not in (20,250)
            or s['phase_error_ps'] not in (0,-140,140) or s['cycles']!=18):
        raise ValueError('Undeclared independent DCC input point')


def parameters(s,phase):
    check(s)
    if phase not in ('P0','P180'):raise ValueError('Unknown DCC input phase')
    period=1e6/s['mhz'];key='r' if phase=='P0' else 'f'
    first=2100+(0 if phase=='P0' else period/2+s['phase_error_ps'])
    return period,first,s[key+'_duty']*period,s[key+'_slew_10_90_ps']/.8


def capture_stop_ps(s):
    # Include both complete final falling ramps and a quiet reset/rearm tail.
    ends=[]
    for phase in ('P0','P180'):
        period,first,high,full=parameters(s,phase)
        ends.append(first+(s['cycles']-1)*period+high+full/2)
    return max(ends)+1000


def points(s,phase):
    period,first,high,full=parameters(s,phase)
    if min(high,period-high)<=full:raise ValueError('DCC input ramps overlap')
    rows=[(0.0,0.0)]
    for k in range(s['cycles']):
        rise=first+k*period;fall=rise+high
        rows += [(rise+(f-.5)*full,1.8*f) for f in (0,.1,.5,.9,1)]
        rows += [(fall+(f-.5)*full,1.8*(1-f)) for f in (0,.1,.5,.9,1)]
    rows.append((capture_stop_ps(s),0.0))
    if any(b[0]<=a[0] for a,b in zip(rows,rows[1:])):raise ValueError('Nonmonotonic DCC source points')
    return rows


def evaluate(t,s,phase,*,independent=False):
    import numpy as np
    if not independent:
        rows=points(s,phase)
        return np.interp(t,[x for x,v in rows],[v for x,v in rows])
    period,first,high,full=parameters(s,phase);value=np.zeros_like(np.asarray(t),dtype=float)
    for k in range(s['cycles']):
        up=np.clip(.5+(t-first-k*period)/full,0,1)
        down=np.clip(.5-(t-first-k*period-high)/full,0,1)
        value+=1.8*np.minimum(up,down)
    return value


def seed_spec(s):
    check(s)
    return dict(process=s['process'],temperature=s['temperature'],mhz=s['mhz'],duty=s['r_duty'],
                slew_ps=s['r_slew_10_90_ps'],phase_error_ps=s['phase_error_ps'],
                buffers=0,drive=1,output_cell='inv_4',reset_drive=1)


def fixture(out,s):
    text=previous.fixture(out,seed_spec(s))
    for instance,phase in (('VP0','P0'),('VP1','P180')):
        pattern=r'(?m)^'+instance+' '+phase+r' 0 PULSE\([^\n]+\)$'
        if len(re.findall(pattern,text))!=1:raise ValueError('Original DCC input source changed')
        block='\n'.join([instance+' '+phase+' 0 PWL(',
            *[f'+ {t:.17g}p {v:.17g}' for t,v in points(s,phase)],'+ )'])
        text=re.sub(pattern,lambda m:block,text,count=1)
    pattern=r'(?m)^\.tran 1p \S+ 0 1p$'
    if len(re.findall(pattern,text))!=1:raise ValueError('Original DCC transient changed')
    text=re.sub(pattern,f'.tran 1p {capture_stop_ps(s):.17g}p 0 1p',text,count=1)
    return text.replace('OpenLVDS '+previous.VERSION,'OpenLVDS '+VERSION,1)
