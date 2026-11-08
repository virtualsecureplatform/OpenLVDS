#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent raw-waveform witness for native two-bank measurements."""
import itertools
import numpy as np
import clocking_profile_300 as policy
from native_binary_raw_v2 import validate
from dcdl_tg_tree_v5 import control_targets
from dcdl_uniform_tree_v3 import encode

VERSION='independent-two-bank-native-waveform-metrology-300-v1'


def transitions(time,voltage,level,up):
    centered=voltage-level
    locations=np.flatnonzero((centered[:-1]<0)&(centered[1:]>=0) if up
                             else (centered[:-1]>0)&(centered[1:]<=0))
    slope=(centered[locations+1]-centered[locations])/(time[locations+1]-time[locations])
    return time[locations]-centered[locations]/slope


def stage(time,inp,out,s,*,ideal_input):
    n=s['cycles'];period=1e6/s['frequency_mhz'];counts={};delays={};slews={};inslews={}
    output_events={};input_events={};input_order=[];output_order=[];absolute=[]
    for edge,up in (('rise',True),('fall',False)):
        ia,im,ib=[transitions(time,inp,v,up) for v in (.18,.9,1.62)]
        oa,om,ob=[transitions(time,out,v,up) for v in (.18,.9,1.62)]
        counts[edge]=dict(input=len(im),input_10_percent=len(ia),input_90_percent=len(ib),
                          output=len(om),output_10_percent=len(oa),output_90_percent=len(ob))
        def full_order(a,m,b):
            return bool(len(a)==len(m)==len(b)==n and
                        np.all((a<m)&(m<b) if up else (b<m)&(m<a)))
        input_order.append(full_order(ia,im,ib));output_order.append(full_order(oa,om,ob))
        delays[edge]=(om-im).tolist() if len(im)==len(om)==n else []
        slews[edge]=np.abs(ob-oa).tolist() if len(oa)==len(ob)==n else []
        inslews[edge]=np.abs(ib-ia).tolist() if len(ia)==len(ib)==n else []
        if len(im)==n:
            expected=2100+(np.arange(n)+(0 if up else s['duty']))*period
            absolute.extend(np.abs(im-expected).tolist())
        input_events[edge]=im;output_events[edge]=om
    complete=all(all(v==n for v in r.values()) for r in counts.values())
    periods={e:(np.diff(v)-period).tolist() for e,v in output_events.items()}
    input_periods={e:(np.diff(v)-period).tolist() for e,v in input_events.items()}
    def peak(values):
        all_values=[v for row in values.values() for v in row]
        return float(np.max(all_values)) if all_values else None
    period_error=peak({e:np.abs(v) for e,v in periods.items()})
    input_period_error=peak({e:np.abs(v) for e,v in input_periods.items()})
    spans={e:float(np.ptp(v)) if len(v)==n else None for e,v in delays.items()}
    high=(output_events['fall']-output_events['rise']).tolist() if complete else []
    low=(output_events['rise'][1:]-output_events['fall'][:-1]).tolist() if complete else []
    max_slew=peak(slews);input_slew=peak(inslews);zero=s['coarse']==s['fine']==0
    head=policy.budgets()['minimum_quarter_ps']-peak(delays) if zero and complete else None
    absolute_pass=bool(complete and absolute and np.max(absolute)<=1) if ideal_input else None
    flags=dict(all_input_output_pulses_present=complete,
        full_swing_pulses_passed=all(input_order+output_order),
        measured_input_contract_passed=bool(all(input_order) and input_slew is not None and input_slew<=250
                                           and input_period_error is not None and input_period_error<=20),
        unwrapped_native_epoch_passed=bool(complete and all(0<v<period for row in delays.values() for v in row)),
        pulse_order_and_widths_passed=bool(complete and all(v>0 for v in high+low)),
        period_screen_passed=bool(complete and period_error is not None and period_error<=20),
        repeated_delay_screen_passed=bool(complete and all(v is not None and v<=20 for v in spans.values())),
        zero_code_quarter_passed=bool(head is not None and head>=0) if zero else True,
        current_downstream_250ps_slew_domain_passed=bool(all(output_order) and max_slew is not None and max_slew<=250))
    return dict(flags,pulse_counts=counts,edge_delays_ps=delays,output_slews_10_90_ps=slews,
        input_slews_10_90_ps=inslews,repeated_delay_span_ps=spans,
        high_widths_ps=high,low_widths_ps=low,period_errors_ps=periods,
        maximum_period_error_ps=period_error,maximum_input_period_error_ps=input_period_error,
        maximum_output_slew_ps=max_slew,maximum_input_slew_ps=input_slew,
        zero_code_fast_quarter_headroom_ps=head,zero_code_quarter_check_required=zero,
        input_reference='ideal_bench' if ideal_input else 'measured_previous_bank_output',
        input_timing_stimulus_passed=absolute_pass,
        stage_transport_passed=bool(all(flags.values()) and (absolute_pass is True if ideal_input else True)))


def electrical(time,get,o,coarse,fine):
    targets=control_targets(coarse,fine);settled=time>=1500
    if np.count_nonzero(settled)==0:raise ValueError('Missing independent settling interval')
    stress=[]
    for d in o['devices']:
        terminals=[get(node) for node in d['terminals']]
        envelope=max(float(np.abs(a-b).max()) for a,b in itertools.combinations(terminals,2))
        stress.append(dict(device=d['name'],maximum_terminal_difference_v=envelope,
                           limit_v=d['limit_v'],passed=bool(envelope<=d['limit_v'])))
    checks={}
    for label,node_key in (('controls','node'),('programming_gates','gate_node')):
        checks[label]=[]
        for control in o[label]:
            v=get(control[node_key])[settled];target=1.8*targets[control['control']]
            error=max(abs(float(v.min())-target),abs(float(v.max())-target))
            checks[label].append(dict(control,maximum_deviation_v=error,passed=bool(error<=.18)))
    return dict(terminal_stress=stress,**checks,terminal_screen_passed=all(r['passed'] for r in stress),
                control_settling_passed=all(r['passed'] for group in checks.values() for r in group))


def measure(folder,observations,s,*,next_coarse,next_fine):
    if set(observations)!={'first','next'}:raise ValueError('Independent witness requires both native bank maps')
    column=lambda n:'v('+n.lower().replace(':','.')+')'
    requested={'v(in)','v(out)','v(next_out)','v(vdd)'}
    for o in observations.values():
        requested.update(column(node) for d in o['devices'] for node in d['terminals'] if node!='0')
        requested.update(column(c['node']) for c in o['controls'])
        requested.update(column(g['gate_node']) for g in o['programming_gates'])
    requested.update(column(pin) for pin in encode(s['coarse'],s['fine']))
    requested.update(column('NEXT_'+pin) for pin in encode(next_coarse,next_fine))
    names,w=validate(folder/'bench.raw',requested,s['stop_ns']*1e-9)
    indices={n:k for k,n in enumerate(names)};time=w[:,indices['time']]*1e12
    if abs(float(time[0]))>1e-6:raise ValueError('Independent witness requires native DC and startup')
    ground=np.zeros(len(time));get=lambda n:ground if n=='0' else w[:,indices[column(n)]]
    banks={}
    for label,start,end,c,f,ideal in (
            ('first','IN','OUT',s['coarse'],s['fine'],True),
            ('next','OUT','NEXT_OUT',next_coarse,next_fine,False)):
        timing=stage(time,get(start),get(end),dict(s,coarse=c,fine=f),ideal_input=ideal)
        checks=electrical(time,get,observations[label],c,f);pins=[]
        for pin,value in encode(c,f).items():
            node=pin if label=='first' else 'NEXT_'+pin
            v=get(node);target=1.8*value
            error=max(abs(float(v.min())-target),abs(float(v.max())-target))
            pins.append(dict(node=node,maximum_deviation_v=error,passed=bool(error<=.01)))
        passed=bool(timing['stage_transport_passed'] and checks['terminal_screen_passed']
                    and checks['control_settling_passed'] and all(p['passed'] for p in pins))
        banks[label]=dict(timing=timing,**checks,external_controls=pins,bank_screen_passed=passed)
    vdd=get('VDD');supply_error=max(abs(float(vdd.min())-1.8),abs(float(vdd.max())-1.8))
    return dict(banks=banks,two_bank_zero_pilot_passed=bool(all(b['bank_screen_passed'] for b in banks.values()) and supply_error<=1e-9),
        maximum_supply_error_v=supply_error,fixed_supply_passed=bool(supply_error<=1e-9),
        startup_samples_retained=True,common_wire_rc_qualified=False,qualified_phy=False,
        scope='Actual two-bank native transport diagnostic only; no shared routing, delay table, DLL/PVT or PHY admission')
