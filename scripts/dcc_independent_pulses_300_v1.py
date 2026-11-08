#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent indexed-interval witness for DCC pulse hold and rearm."""
import numpy as np
from two_bank_independent_measure_300_v1 import transitions


def pulse_generator(t,clock,pulse,reset,s):
    count=s['cycles'];rise=transitions(t,clock,.9,True);fall=transitions(t,clock,.9,False)
    start=transitions(t,pulse,.9,True);end=transitions(t,pulse,.9,False)
    complete=all(len(v)==count for v in (rise,fall,start,end));rows=[]
    if complete:
        next_edges=np.concatenate([rise[1:],[t[-1]]])
        for edge,falling,following in zip(rise,fall,next_edges):
            a,b=np.searchsorted(start,[edge,following],side='left')
            a=int(np.searchsorted(start,edge,side='right'))
            c,d=np.searchsorted(end,[edge,following],side='left')
            c=int(np.searchsorted(end,edge,side='right'))
            unique=b-a==d-c==1
            ordered=bool(unique and edge<start[a]<end[c]<falling<following)
            left=int(np.searchsorted(t,end[c]+20,side='right')) if unique else 0
            right=int(np.searchsorted(t,falling-20,side='left')) if unique else 0
            samples=max(0,right-left)
            held_peak=float(reset[left:right].max()) if samples else None
            before=int(np.searchsorted(t,edge-40,side='left'));after=int(np.searchsorted(t,edge-20,side='right'))
            armed_floor=float(reset[before:after].min()) if after>before else None
            held=bool(ordered and held_peak is not None and held_peak<=.18)
            armed=bool(armed_floor is not None and armed_floor>=1.62)
            rows.append(dict(source_edge_ps=float(edge),source_fall_ps=float(falling),
                pulse_count=int(b-a),pulse_end_count=int(d-c),pulse_order_passed=ordered,
                held_interval_samples=samples,maximum_held_reset_v=held_peak,minimum_pre_edge_reset_v=armed_floor,
                reset_held_until_fall=held,rearmed_before_edge=armed,passed=bool(held and armed)))
    return dict(input_rise_count=len(rise),input_fall_count=len(fall),pulse_rise_count=len(start),pulse_fall_count=len(end),
        complete_all_startup_events=bool(complete),events=rows,
        pulse_generator_integrity_passed=bool(complete and all(r['passed'] for r in rows)))
