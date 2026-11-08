#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Two-bank native transport and terminal checks; no shared-wire/PHY admission."""
import numpy as np
import clocking_profile_300 as policy
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from dcdl_tg_tree_v5 import control_targets
from dcdl_uniform_tree_v3 import encode

VERSION='two-native-bank-relative-transport-metrology-300-v1'


def stage(t,inp,out,s,*,ideal_input):
    """Retain all startup events; use the measured input for a downstream bank."""
    count=s['cycles'];period=1e6/s['frequency_mhz']
    events={};inputs={};counts={};delays={};slews={};input_slews={}
    output_order=True;input_order=True;absolute_errors=[]
    for up,edge in ((True,'rise'),(False,'fall')):
        a=crossings(t,inp,.9,up);b=crossings(t,out,.9,up)
        il=crossings(t,inp,.18,up);ih=crossings(t,inp,1.62,up)
        lo=crossings(t,out,.18,up);hi=crossings(t,out,1.62,up)
        counts[edge]=dict(input=len(a),input_10_percent=len(il),input_90_percent=len(ih),
                          output=len(b),output_10_percent=len(lo),output_90_percent=len(hi))
        def ordered(low,mid,high):
            return len(low)==len(mid)==len(high)==count and all(
                x<z<y if up else y<z<x for x,z,y in zip(low,mid,high))
        input_order=input_order and ordered(il,a,ih)
        output_order=output_order and ordered(lo,b,hi)
        delays[edge]=[y-x for x,y in zip(a,b)] if len(a)==len(b)==count else []
        slews[edge]=[abs(y-x) for x,y in zip(lo,hi)] if len(lo)==len(hi)==count else []
        input_slews[edge]=[abs(y-x) for x,y in zip(il,ih)] if len(il)==len(ih)==count else []
        expected=[2100+(k+(0 if up else s['duty']))*period for k in range(count)]
        if len(a)==count:absolute_errors.extend(abs(x-y) for x,y in zip(a,expected))
        events[edge]=b;inputs[edge]=a
    complete=all(all(v==count for v in row.values()) for row in counts.values())
    maximum=lambda values:max((v for vs in values.values() for v in vs),default=None)
    spans={e:max(v)-min(v) if len(v)==count else None for e,v in delays.items()}
    periods={e:[y-x-period for x,y in zip(v,v[1:])] for e,v in events.items()}
    input_periods={e:[y-x-period for x,y in zip(v,v[1:])] for e,v in inputs.items()}
    error=maximum({e:[abs(x) for x in v] for e,v in periods.items()})
    input_error=maximum({e:[abs(x) for x in v] for e,v in input_periods.items()})
    high=[b-a for a,b in zip(events['rise'],events['fall'])] if complete else []
    low=[a-b for a,b in zip(events['rise'][1:],events['fall'][:-1])] if complete else []
    max_slew=maximum(slews);input_slew=maximum(input_slews)
    input_contract=bool(input_order and input_slew is not None and input_slew<=250
                        and input_error is not None and input_error<=20)
    stimulus=bool(complete and absolute_errors and max(absolute_errors)<=1) if ideal_input else None
    zero=s['coarse']==s['fine']==0
    room=policy.budgets()['minimum_quarter_ps']-maximum(delays) if complete and zero else None
    checks=dict(all_input_output_pulses_present=complete,full_swing_pulses_passed=bool(input_order and output_order),
        measured_input_contract_passed=input_contract,
        unwrapped_native_epoch_passed=bool(complete and all(0<v<period for vs in delays.values() for v in vs)),
        pulse_order_and_widths_passed=bool(complete and all(v>0 for v in high+low)),
        period_screen_passed=bool(complete and error is not None and error<=20),
        repeated_delay_screen_passed=bool(complete and all(v is not None and v<=20 for v in spans.values())),
        zero_code_quarter_passed=bool(room is not None and room>=0) if zero else True,
        current_downstream_250ps_slew_domain_passed=bool(output_order and max_slew is not None and max_slew<=250))
    return dict(checks,pulse_counts=counts,edge_delays_ps=delays,output_slews_10_90_ps=slews,
        input_slews_10_90_ps=input_slews,repeated_delay_span_ps=spans,
        high_widths_ps=high,low_widths_ps=low,period_errors_ps=periods,
        maximum_period_error_ps=error,maximum_input_period_error_ps=input_error,
        maximum_output_slew_ps=max_slew,maximum_input_slew_ps=input_slew,
        zero_code_fast_quarter_headroom_ps=room,zero_code_quarter_check_required=zero,
        input_reference='ideal_bench' if ideal_input else 'measured_previous_bank_output',
        input_timing_stimulus_passed=stimulus,
        stage_transport_passed=bool(all(checks.values()) and (stimulus is True if ideal_input else True)))


def electrical(t,get,o,coarse,fine):
    """Complete native terminal envelope and independently programmed controls."""
    targets=control_targets(coarse,fine);settled=t>=1500
    if not np.any(settled):raise ValueError('Missing control-settling interval')
    stress=[]
    for d in o['devices']:
        voltages=[get(n) for n in d['terminals']]
        peak=float(np.max(np.maximum.reduce(voltages)-np.minimum.reduce(voltages)))
        stress.append(dict(device=d['name'],maximum_terminal_difference_v=peak,
                           limit_v=d['limit_v'],passed=bool(peak<=d['limit_v'])))
    checks={}
    for category,key in (('controls','node'),('programming_gates','gate_node')):
        checks[category]=[]
        for c in o[category]:
            target=1.8*targets[c['control']]
            deviation=float(np.max(np.abs(get(c[key])[settled]-target)))
            checks[category].append(dict(c,maximum_deviation_v=deviation,passed=bool(deviation<=.18)))
    return dict(terminal_stress=stress,**checks,
        terminal_screen_passed=all(r['passed'] for r in stress),
        control_settling_passed=all(r['passed'] for rows in checks.values() for r in rows))


def measure(folder,observations,s,*,next_coarse,next_fine):
    if set(observations)!={'first','next'}:raise ValueError('Require separate complete native bank maps')
    column=lambda n:'v('+n.replace(':','.').lower()+')'
    required={'v(in)','v(out)','v(next_out)','v(vdd)'}
    for o in observations.values():
        required.update(column(n) for d in o['devices'] for n in d['terminals'] if n!='0')
        required.update(column(c['node']) for c in o['controls'])
        required.update(column(g['gate_node']) for g in o['programming_gates'])
    required.update(column(pin) for pin in encode(s['coarse'],s['fine']))
    required.update(column('NEXT_'+pin) for pin in encode(next_coarse,next_fine))
    names,w=validate(folder/'bench.raw',required,s['stop_ns']*1e-9)
    idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12
    if abs(t[0])>1e-6:raise ValueError('Two-bank trace omits native DC/startup sample')
    zero=np.zeros(len(t));get=lambda n:zero if n=='0' else w[:,idx[column(n)]]
    rows={}
    for label,a,b,c,f,ideal in (
            ('first','IN','OUT',s['coarse'],s['fine'],True),
            ('next','OUT','NEXT_OUT',next_coarse,next_fine,False)):
        spec=dict(s,coarse=c,fine=f)
        timing=stage(t,get(a),get(b),spec,ideal_input=ideal)
        checks=electrical(t,get,observations[label],c,f)
        external=[]
        for pin,value in encode(c,f).items():
            node=pin if label=='first' else 'NEXT_'+pin
            deviation=float(np.max(np.abs(get(node)-1.8*value)))
            external.append(dict(node=node,maximum_deviation_v=deviation,passed=bool(deviation<=.01)))
        passed=bool(timing['stage_transport_passed'] and checks['terminal_screen_passed']
                    and checks['control_settling_passed'] and all(r['passed'] for r in external))
        rows[label]=dict(timing=timing,**checks,external_controls=external,bank_screen_passed=passed)
    return dict(banks=rows,two_bank_zero_pilot_passed=bool(all(r['bank_screen_passed'] for r in rows.values())
            and np.max(np.abs(get('VDD')-1.8))<=1e-9),
        maximum_supply_error_v=float(np.max(np.abs(get('VDD')-1.8))),
        fixed_supply_passed=bool(np.max(np.abs(get('VDD')-1.8))<=1e-9),
        startup_samples_retained=True,common_wire_rc_qualified=False,qualified_phy=False,
        scope='Actual two-bank native transport diagnostic only; no shared routing, delay table, DLL/PVT or PHY admission')
