# SPDX-License-Identifier: GPL-3.0-only
"""Stable DLL case names and mean duty from an integral captured clock span."""
import csv


def case_name(process, temperature, mhz=400, duty=.5):
    duty=round(float(duty),6)
    suffix='' if mhz==400 else f'_{mhz:g}m'
    if duty!=.5:suffix+='_d'+f'{duty:.6f}'.replace('.','p')
    return f'dll_{process}_{temperature}'+suffix


def trace_duty(path):
    with path.open() as stream:
        rows=csv.reader(stream);next(rows)
        events=[(float(t),int(float(v))) for t,v in rows]
    rises=[i for i,(_,v) in enumerate(events) if v==1]
    if len(rises)<2:raise ValueError('Clock duty requires two rising edges')
    first,last=rises[0],rises[-1]
    span=events[last][0]-events[first][0]
    if span<=0:raise ValueError('Clock trace must advance in time')
    high=sum(events[i+1][0]-events[i][0] for i in range(first,last) if events[i][1]==1)
    return round(high/span,6)
