#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure actual chain/DCC transport while keeping phase qualification separate."""
import numpy as np
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
import four_bank_native_measure_300_v1 as chain

VERSION='startup-inclusive-source-dcc-four-section-measure-300-v1'


def events(t,a,b,q,s):
    count=s['cycles'];period=1e6/s['frequency_mhz']
    inputs=[crossings(t,v,.9,True) for v in (a,b)]
    source=sorted(x for v in inputs for x in v)
    edges={edge:crossings(t,q,.9,up) for edge,up in (('rise',True),('fall',False))}
    output=sorted((x,edge) for edge,values in edges.items() for x in values)
    complete=all(len(v)==count for v in inputs) and all(len(v)==count for v in edges.values())
    checks=[];delays=[]
    if complete:
        for k,((time,edge),reference) in enumerate(zip(output,source)):
            # Reset makes Q high. Each rising source event must produce one
            # alternating transition before the next source event, including
            # the very first event. No startup/late-event exclusion is used.
            end=source[k+1] if k+1<len(source) else t[-1]
            passed=reference<time<end and edge==('fall' if k%2==0 else 'rise')
            checks.append(bool(passed));delays.append(time-reference)
    slew=[];swing=True
    for edge,up in (('rise',True),('fall',False)):
        lo=crossings(t,q,.18,up);hi=crossings(t,q,1.62,up);mid=edges[edge]
        valid=len(lo)==len(mid)==len(hi)==count
        if valid:
            valid=all(x<y<z if up else z<y<x for x,y,z in zip(lo,mid,hi))
            slew.extend(abs(y-x) for x,y in zip(lo,hi))
        swing=swing and valid
    widths={'high':[],'low':[]}
    for (x,edge),(y,_) in zip(output,output[1:]):widths['high' if edge=='rise' else 'low'].append(y-x)
    mean_errors={k:abs(float(np.mean(v))-period/2) if v else None for k,v in widths.items()}
    period_errors=[abs(y-x-period) for v in edges.values() for x,y in zip(v,v[1:])]
    maximum_slew=max(slew,default=None);maximum_period=max(period_errors,default=None)
    return dict(source_rise_counts=[len(v) for v in inputs],output_edge_counts={k:len(v) for k,v in edges.items()},
        startup_reset_output_high=bool(q[0]>=1.62),complete_events=bool(complete),
        event_pair_checks=checks,event_latency_ps=delays,
        one_transition_per_source_event_passed=bool(complete and all(checks) and q[0]>=1.62),
        full_swing_passed=bool(swing),maximum_output_slew_ps=maximum_slew,
        output_slew_passed=bool(swing and maximum_slew is not None and maximum_slew<=250),
        high_low_widths_ps=widths,mean_half_cycle_error_ps=mean_errors,
        maximum_period_error_ps=maximum_period,
        period_screen_passed=bool(complete and maximum_period is not None and maximum_period<=20),
        observed_mean_half_cycle_passed=bool(complete and all(v is not None and v<=50 for v in mean_errors.values())))


def measure(folder,observations,s):
    if set(observations)!={'sections','dcc'} or set(observations['dcc'])!={'0','1'}:
        raise ValueError('Require complete chain and both actual source DCC maps')
    result=chain.measure(folder,observations['sections'],s)
    column=lambda n:'v('+n.replace(':','.').lower()+')'
    required={column(n) for n in ('IN','OUT','B1_OUT','B2_OUT','DCC0_OUT','DCC1_OUT','DCC_RESET_N')}
    all_names=[d['name'] for o in list(observations['sections'].values())+list(observations['dcc'].values()) for d in o['devices']]
    if len(all_names)!=len(set(all_names)):raise ValueError('Colliding chain/DCC native device identities')
    for k,(a,b) in enumerate((('IN','B1_OUT'),('OUT','B2_OUT'))):
        o=observations['dcc'][str(k)]
        if o['input_nodes']!=[a,b] or o['output_node']!=f'DCC{k}_OUT' or not o['devices']:
            raise ValueError('Actual DCC phase connection or device map changed')
        required.update(column(n) for d in o['devices']+o['passive_resistors'] for n in d['terminals'] if n!='0')
    names,w=validate(folder/'bench.raw',required,s['stop_ns']*1e-9)
    index={n:k for k,n in enumerate(names)};t=w[:,index['time']]*1e12
    zero=np.zeros(len(t));get=lambda n:zero if n=='0' else w[:,index[column(n)]]
    reset=1.8*np.clip((t-1000)/20,0,1);reset_error=float(np.max(np.abs(get('DCC_RESET_N')-reset)))
    rows={}
    for k in ('0','1'):
        o=observations['dcc'][k];timing=events(t,*[get(n) for n in o['input_nodes']],get(o['output_node']),s)
        stress=[]
        for d in o['devices']:
            v=[get(n) for n in d['terminals']]
            peak=float(np.max(np.maximum.reduce(v)-np.minimum.reduce(v)))
            stress.append(dict(device=d['name'],maximum_terminal_difference_v=peak,limit_v=d['limit_v'],passed=bool(peak<=d['limit_v'])))
        passed=bool(reset_error<=1e-9 and all(r['passed'] for r in stress) and all(timing[n] for n in (
            'one_transition_per_source_event_passed','full_swing_passed','output_slew_passed','period_screen_passed')))
        rows[k]=dict(timing=timing,terminal_stress=stress,terminal_screen_passed=all(r['passed'] for r in stress),
                     source_dcc_transport_passed=passed)
    return dict(chain=result,dcc=rows,maximum_reset_source_error_v=reset_error,
        combined_loading_transport_passed=bool(result['four_section_transport_passed'] and all(r['source_dcc_transport_passed'] for r in rows.values())),
        observed_mean_half_cycle_passed=all(r['timing']['observed_mean_half_cycle_passed'] for r in rows.values()),
        calibrated_phase_qualified=False,detector_fanout_qualified=False,shared_wire_rc_qualified=False,qualified_phy=False,
        scope='Startup-inclusive actual source-DCC/chain transport only; phase calibration, detector, routing and PHY remain required')
