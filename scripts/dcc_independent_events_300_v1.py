#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent vectorized threshold witness for combined source-DCC events."""
import numpy as np
from two_bank_independent_measure_300_v1 import transitions


def events(t,a,b,q,s):
    count=s['cycles'];period=1e6/s['frequency_mhz']
    inputs=[transitions(t,v,.9,True) for v in (a,b)]
    source=np.sort(np.concatenate(inputs))
    edge_times={edge:transitions(t,q,.9,up) for edge,up in (('rise',True),('fall',False))}
    times=np.concatenate([edge_times['rise'],edge_times['fall']])
    directions=np.concatenate([np.ones(len(edge_times['rise']),dtype=bool),np.zeros(len(edge_times['fall']),dtype=bool)])
    order=np.argsort(times,kind='stable');times=times[order];directions=directions[order]
    complete=all(len(v)==count for v in inputs+list(edge_times.values()))
    checks=[];latencies=[]
    if complete:
        ends=np.concatenate([source[1:],[t[-1]]])
        checks=((source<times)&(times<ends)&(directions==(np.arange(2*count)%2==1))).tolist()
        latencies=(times-source).tolist()
    swing=[];slews=[]
    for edge,up in (('rise',True),('fall',False)):
        low=transitions(t,q,.18,up);high=transitions(t,q,1.62,up);middle=edge_times[edge]
        full=len(low)==len(middle)==len(high)==count
        if full:
            full=bool(np.all((low<middle)&(middle<high) if up else (high<middle)&(middle<low)))
            slews.extend(np.abs(high-low).tolist())
        swing.append(full)
    widths=np.diff(times)
    high_low={name:widths[directions[:-1]==up].tolist() for name,up in (('high',True),('low',False))}
    mean={name:abs(float(np.mean(v))-period/2) if v else None for name,v in high_low.items()}
    period_errors=np.concatenate([np.abs(np.diff(v)-period) for v in edge_times.values()])
    maximum_period=float(period_errors.max()) if len(period_errors) else None
    maximum_slew=max(slews,default=None)
    return dict(source_rise_counts=[len(v) for v in inputs],output_edge_counts={k:len(v) for k,v in edge_times.items()},
        startup_reset_output_high=bool(q[0]>=1.62),complete_events=bool(complete),
        event_pair_checks=checks,event_latency_ps=latencies,
        one_transition_per_source_event_passed=bool(complete and all(checks) and q[0]>=1.62),
        full_swing_passed=bool(all(swing)),maximum_output_slew_ps=maximum_slew,
        output_slew_passed=bool(all(swing) and maximum_slew is not None and maximum_slew<=250),
        high_low_widths_ps=high_low,mean_half_cycle_error_ps=mean,
        maximum_period_error_ps=maximum_period,
        period_screen_passed=bool(complete and maximum_period is not None and maximum_period<=20),
        observed_mean_half_cycle_passed=bool(complete and all(v is not None and v<=50 for v in mean.values())))
