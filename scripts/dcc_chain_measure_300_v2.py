#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Add all-event source pulse-generator hold/rearm checks to combined transport."""
import numpy as np
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
import dcc_chain_measure_300_v1 as previous

VERSION='startup-inclusive-source-dcc-four-section-pulse-measure-300-v2'


def pulse_generator(t,clock,pulse,reset,s):
    count=s['cycles'];rise=crossings(t,clock,.9,True);fall=crossings(t,clock,.9,False)
    start=np.asarray(crossings(t,pulse,.9,True));end=np.asarray(crossings(t,pulse,.9,False))
    complete=len(rise)==len(fall)==len(start)==len(end)==count
    rows=[]
    if complete:
        for k,(edge,falling) in enumerate(zip(rise,fall)):
            following=rise[k+1] if k+1<count else t[-1]
            starts=start[(start>edge)&(start<following)]
            ends=end[(end>edge)&(end<following)]
            unique=len(starts)==len(ends)==1
            ordered=bool(unique and edge<starts[0]<ends[0]<falling<following)
            held_mask=(t>ends[0]+20)&(t<falling-20) if unique else np.zeros(len(t),dtype=bool)
            armed_mask=(t>=edge-40)&(t<=edge-20)
            held_peak=float(np.max(reset[held_mask])) if np.any(held_mask) else None
            armed_floor=float(np.min(reset[armed_mask])) if np.any(armed_mask) else None
            held=bool(ordered and held_peak is not None and held_peak<=.18)
            armed=bool(armed_floor is not None and armed_floor>=1.62)
            rows.append(dict(source_edge_ps=float(edge),source_fall_ps=float(falling),
                pulse_count=len(starts),pulse_end_count=len(ends),pulse_order_passed=ordered,
                held_interval_samples=int(np.count_nonzero(held_mask)),
                maximum_held_reset_v=held_peak,minimum_pre_edge_reset_v=armed_floor,
                reset_held_until_fall=held,rearmed_before_edge=armed,passed=bool(held and armed)))
    return dict(input_rise_count=len(rise),input_fall_count=len(fall),pulse_rise_count=len(start),pulse_fall_count=len(end),
        complete_all_startup_events=bool(complete),events=rows,
        pulse_generator_integrity_passed=bool(complete and all(r['passed'] for r in rows)))


def measure(folder,observations,s):
    result=previous.measure(folder,observations,s)
    column=lambda n:'v('+n.replace(':','.').lower()+')'
    required={column(n) for n in ('IN','OUT','B1_OUT','B2_OUT')}
    required.update(column(f'XDC{k}:{n}') for k in range(2) for n in ('a','b','areset','breset'))
    names,w=validate(folder/'bench.raw',required,s['stop_ns']*1e-9)
    index={n:k for k,n in enumerate(names)};t=w[:,index['time']]*1e12
    get=lambda n:w[:,index[column(n)]]
    for k in ('0','1'):
        row=result['dcc'][k];checks={}
        for channel,node in zip(('a','b'),observations['dcc'][k]['input_nodes']):
            checks[channel]=pulse_generator(t,get(node),get(f'XDC{k}:{channel}'),get(f'XDC{k}:{channel}reset'),s)
        passed=all(v['pulse_generator_integrity_passed'] for v in checks.values())
        row.update(pulse_generators=checks,pulse_generator_integrity_passed=passed,
                   source_dcc_transport_passed=bool(row['source_dcc_transport_passed'] and passed))
    result['combined_loading_transport_passed']=bool(result['chain']['four_section_transport_passed'] and
        all(r['source_dcc_transport_passed'] for r in result['dcc'].values()))
    return result
