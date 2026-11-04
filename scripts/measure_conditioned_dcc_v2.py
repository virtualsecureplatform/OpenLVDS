# SPDX-License-Identifier: GPL-3.0-only
"""Actual-crossing DCC event, polarity, pulse-width and MOS-terminal analysis."""
import itertools
import numpy as np
from run_ngspice import read_raw
from probe_digital_dcc_v2 import crossings


def measure(folder,spec,devices,scope):
    names,w=read_raw(folder/'bench.raw');idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12
    period=1e6/spec['mhz'];origin=spec['raw_start_ns']*1000;stop=origin+22*period
    if not np.isfinite(w).all() or t[-1]<stop-.01:raise ValueError('Incomplete/nonfinite DCC transient')
    def get(n):return w[:,idx['v('+n.replace(':','.').lower()+')']]
    def edges(n,up=True):return crossings(t,get(n),up)
    release=edges('RESET_N')
    if len(release)!=1:raise ValueError('Reset release count')
    e0,e1=edges('P0'),edges('P180');qr,qf=edges('Q'),edges('Q',False)
    output=np.sort(np.r_[qr,qf]);source=sorted([(float(e),'P0') for e in e0 if e>release[0]]+[(float(e),'P180') for e in e1 if e>release[0]])
    checks=[];latency=[]
    for (a,phase),(b,_) in zip(source,source[1:]):
        all_edges=output[(output>a)&(output<b)];direction=qr if phase=='P0' else qf;valid=direction[(direction>a)&(direction<b)]
        checks.append(dict(source_edge_ps=a,phase=phase,output_count=len(all_edges),direction_count=len(valid),passed=len(all_edges)==1 and len(valid)==1))
        if len(all_edges)==1:latency.append(float(all_edges[0]-a))
    startup=bool(source and source[0][1]=='P180' and not np.any(output<source[0][0]))
    durations=[]
    for first,second in [(qr,qf),(qf,qr)]:
        widths=[]
        for a in first[(first>=origin+8*period)&(first<stop-period)]:
            following=second[second>a]
            if len(following):widths.append(float(following[0]-a))
        durations.append(widths)
    half=max(abs(float(np.mean(d))-period/2) for d in durations) if all(durations) else None
    zeros=np.zeros(len(t));peak=0.;worst=None;groups={};health=True;stress=[]
    for device in devices:
        values=[zeros if n=='0' else get(n) for n in device['terminals']]
        group=device['name'].split(':')[0];local_peak=0.
        for a,b in itertools.combinations(range(4),2):
            delta=np.abs(values[a]-values[b]);value=float(np.max(delta));groups[group]=max(value,groups.get(group,0));local_peak=max(local_peak,value)
            if value>peak:
                j=int(np.argmax(delta));peak=value;worst=dict(device=device['name'],model=device['model'],terminal_pair=[a,b],
                    nodes=[device['terminals'][a],device['terminals'][b]],time_ps=float(t[j]),voltages_v=[float(values[a][j]),float(values[b][j])])
        ok=local_peak<=device['limit_v'];health=health and ok
        stress.append(dict(device=device['name'],max_terminal_difference_v=local_peak,limit_v=device['limit_v'],passed=ok))
    request=edges('REQUEST')
    if len(request)!=1:raise ValueError('Run request edge count')
    clk0=e0[(e0>request[0])&(e0<release[0])]
    reset_after_two_edges=bool(len(clk0)>=2)
    common=get('XF:VCM')[t>=origin];common_ok=bool(np.max(np.abs(common-.9))<=.01)
    passed=bool(checks and all(c['passed'] for c in checks) and startup and reset_after_two_edges and common_ok and half is not None and half<=50 and health)
    return dict(output_event_checks=checks,event_integrity_passed=bool(checks and all(c['passed'] for c in checks)),startup_passed=startup,
        actual_source_half_spacing_error_ps=max(abs((b-a)-period/2) for (a,_),(b,_) in zip(source,source[1:])),
        half_cycle_error_ps=half,half_cycle_passed=bool(half is not None and half<=50),
        half_cycle_width_ranges_ps=[[min(d),max(d)] if d else None for d in durations],
        maximum_individual_half_cycle_error_ps=max(abs(v-period/2) for d in durations for v in d) if all(durations) else None,
        output_latency_range_ps=[min(latency),max(latency)] if latency else None,terminal_abs_peak_v=peak,terminal_peak_location=worst,
        terminal_group_peaks_v=groups,terminal_stress=stress,terminal_screen_passed=bool(health),
        reset_after_two_clock_edges_passed=reset_after_two_edges,reset_release_time_ps=float(release[0]),
        common_mode_passed=common_ok,common_mode_range_v=[float(common.min()),float(common.max())],
        pilot_passed=passed,qualified_phy=False,scope=scope)
