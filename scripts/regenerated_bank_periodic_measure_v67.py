# SPDX-License-Identifier: GPL-3.0-only
"""Complete native periodic transport, all MOS terminals, controls and slew."""
import itertools
import numpy as np
from native_binary_raw_v2 import validate
from dcdl_tg_tree_v5 import control_targets
import probe_dcdl_uniform_tree_v3 as baseline


def crossings(t,v,level,rising):
    idx=np.nonzero((v[:-1]<level)&(v[1:]>=level) if rising else (v[:-1]>level)&(v[1:]<=level))[0]
    return [float(t[k]+(level-v[k])*(t[k+1]-t[k])/(v[k+1]-v[k])) for k in idx]


def timing(t,inp,out,s):
    count=s['cycles'];period=1e6/s['frequency_mhz'];events={};delays={};slews={};counts={}
    input_errors=[];ordered=True
    for up,edge in ((True,'rise'),(False,'fall')):
        a=crossings(t,inp,.9,up);b=crossings(t,out,.9,up)
        low=crossings(t,out,.18,up);high=crossings(t,out,1.62,up)
        counts[edge]=dict(input=len(a),output=len(b),output_10_percent=len(low),output_90_percent=len(high))
        delays[edge]=[y-x for x,y in zip(a,b)] if len(a)==len(b)==count else []
        slews[edge]=[abs(y-x) for x,y in zip(low,high)] if len(low)==len(high)==count else []
        if len(low)==len(high)==len(b)==count:
            ordered=ordered and all(x<z<y if up else y<z<x for x,z,y in zip(low,b,high))
        else:ordered=False
        expected=[2100+(k+(0 if up else s['duty']))*period for k in range(count)]
        input_errors += [abs(x-y) for x,y in zip(a,expected)] if len(a)==count else [float('inf')]
        events[edge]=b
    pulse_counts=all(v['input']==v['output']==count for v in counts.values())
    full_swing=ordered and all(v['output_10_percent']==v['output_90_percent']==count for v in counts.values())
    unwrapped=pulse_counts and all(0<v<period for vs in delays.values() for v in vs)
    highs=[];lows=[]
    if pulse_counts:
        highs=[b-a for a,b in zip(events['rise'],events['fall'])]
        lows=[events['rise'][k+1]-events['fall'][k] for k in range(count-1)]
    integrity=bool(pulse_counts and all(v>0 for v in highs+lows))
    periods={edge:[b-a-period for a,b in zip(vs,vs[1:])] for edge,vs in events.items()}
    period_error=max((abs(v) for vs in periods.values() for v in vs),default=None)
    spans={edge:max(vs)-min(vs) if len(vs)==count else None for edge,vs in delays.items()}
    repeat=pulse_counts and all(v is not None and v<=20 for v in spans.values())
    max_slew=max((v for vs in slews.values() for v in vs),default=None)
    slew_domain=bool(full_swing and max_slew is not None and max_slew<=250)
    zero=s['coarse']==s['fine']==0
    headroom=1e6/410/4-max(v for vs in delays.values() for v in vs) if zero and pulse_counts else None
    quarter=bool(headroom is not None and headroom>=0) if zero else True
    return dict(pulse_counts=counts,all_input_output_pulses_present=pulse_counts,
        input_timing_stimulus_passed=bool(max(input_errors,default=float('inf'))<=1),
        full_swing_pulses_passed=full_swing,unwrapped_native_epoch_passed=unwrapped,pulse_order_and_widths_passed=integrity,
        edge_delays_ps=delays,output_slews_10_90_ps=slews,maximum_output_slew_ps=max_slew,
        current_downstream_250ps_slew_domain_passed=slew_domain,
        downstream_slew_domain_widening_required=bool(full_swing and max_slew is not None and max_slew>250),
        high_widths_ps=highs,low_widths_ps=lows,output_duty_percent=[100*v/period for v in highs],
        period_errors_ps=periods,maximum_period_error_ps=period_error,
        period_screen_passed=bool(pulse_counts and period_error is not None and period_error<=20),
        repeated_delay_span_ps=spans,repeated_delay_screen_passed=repeat,
        zero_code_quarter_check_required=zero,zero_code_fast_quarter_headroom_ps=headroom,zero_code_quarter_passed=quarter)


def measure(folder,i):
    s=i['spec'];o=i['observations'];targets=control_targets(s['coarse'],s['fine'])
    def column(n):return 'v('+n.replace(':','.').lower()+')'
    requested={column(n) for d in o['devices'] for n in d['terminals'] if n!='0'}
    requested.update(column(c['node']) for c in o['controls'])
    requested.update(column(n) for n in ('IN','OUT','VDD',*baseline.circuit.encode(s['coarse'],s['fine'])))
    names,w=validate(folder/'bench.raw',requested,s['stop_ns']*1e-9);idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12
    if t[0]>1e-6:raise ValueError('Periodic native trace omits startup interval')
    def get(n):return np.zeros(len(t)) if n=='0' else w[:,idx[column(n)]]
    r=timing(t,get('IN'),get('OUT'),s);stress=[];controls=[];gates=[];stable=t>=1500
    for d in o['devices']:
        peak=max(float(np.max(np.abs(get(a)-get(b)))) for a,b in itertools.combinations(d['terminals'],2))
        stress.append(dict(device=d['name'],maximum_terminal_difference_v=peak,limit_v=d['limit_v'],passed=bool(peak<=d['limit_v'])))
    for c in o['controls']:
        deviation=float(np.max(np.abs(get(c['node'])[stable]-1.8*targets[c['control']])))
        controls.append(dict(c,maximum_deviation_v=deviation,passed=bool(deviation<=.18)))
    for g in o['programming_gates']:
        deviation=float(np.max(np.abs(get(g['gate_node'])[stable]-1.8*targets[g['control']])))
        gates.append(dict(g,maximum_deviation_v=deviation,passed=bool(deviation<=.18)))
    for pin,value in baseline.circuit.encode(s['coarse'],s['fine']).items():
        if np.max(np.abs(get(pin)-1.8*value))>.01:raise ValueError('Periodic external control stimulus changed')
    r.update(terminal_stress=stress,controls=controls,programming_gates=gates,
        terminal_screen_passed=all(d['passed'] for d in stress),control_settling_passed=all(c['passed'] for c in controls+gates))
    keys=('all_input_output_pulses_present','input_timing_stimulus_passed','full_swing_pulses_passed','unwrapped_native_epoch_passed',
          'pulse_order_and_widths_passed','period_screen_passed','repeated_delay_screen_passed','zero_code_quarter_passed',
          'terminal_screen_passed','control_settling_passed')
    r.update(periodic_transport_screen_passed=all(r[k] for k in keys),whole_bank_rc_retained=True,
             corrected_dcc_output_qualified=False,all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False)
    r['current_clock_interface_screen_passed']=r['periodic_transport_screen_passed'] and r['current_downstream_250ps_slew_domain_passed']
    return r
