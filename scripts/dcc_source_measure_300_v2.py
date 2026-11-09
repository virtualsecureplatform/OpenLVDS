#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Startup-inclusive corrected DCC source event/reset/timing screen."""
import numpy as np
import dcc_input_measure_300_v2 as inputs


def measure(names,w,s,*,independent=False):
    source=inputs.measure(names,w,s,independent=independent)
    nodes=('q','xd.events','xd.a','xd.b','xd.areset','xd.breset','vdd')
    if not {'v('+n+')' for n in nodes}<=set(names):raise ValueError('Missing complete DCC source observations')
    t=w[:,names.index('time')]*1e12;get=lambda n:w[:,names.index('v('+n+')')]
    edge=lambda n,level,up:inputs.edge_times(t,get(n),level,up,independent)
    rises={n:edge(n,.9,True) for n in ('p0','p180')}
    falls={n:edge(n,.9,False) for n in ('p0','p180')}
    events=np.sort(np.r_[rises['p0'],rises['p180']]);pulse=edge('xd.events',.9,True)
    q_up=edge('q',.9,True);q_down=edge('q',.9,False);q=np.sort(np.r_[q_up,q_down])
    def window(node,a,b,inclusive=False):
        v=get(node)
        if independent:
            left=np.searchsorted(t,a,side='left' if inclusive else 'right')
            right=np.searchsorted(t,b,side='right' if inclusive else 'left')
            return v[left:right]
        return v[((t>=a)&(t<=b)) if inclusive else ((t>a)&(t<b))]
    def swing(node,count):
        return all(len(edge(node,level,up))==count for level in (.18,.9,1.62) for up in (True,False))
    event_checks=[]
    for k,at in enumerate(events):
        nxt=events[k+1] if k+1<len(events) else t[-1]
        a=pulse[(pulse>at)&(pulse<nxt)];b=q[(q>at)&(q<nxt)]
        event_checks.append(dict(source_ps=float(at),pulse_count=len(a),output_count=len(b),passed=bool(len(a)==len(b)==1)))
    event_ok=bool(len(events)==len(pulse)==len(q)==36 and all(c['passed'] for c in event_checks)
                  and len(q_up)==len(q_down)==18 and swing('xd.events',36))
    # Reset defines an initially high output; source events must alternate fall/rise.
    starts=[inputs.reference.parameters(s,phase)[1]-inputs.reference.parameters(s,phase)[3]/2 for phase in ('P0','P180')]
    initial=window('q',0,min(starts),inclusive=True)
    initial_ok=bool(len(initial) and initial.min()>=1.62)
    order_ok=bool(len(q)==36 and np.array_equal(q[::2],q_down) and np.array_equal(q[1::2],q_up))
    pulse_checks=[]
    for node,tag in (('p0','a'),('p180','b')):
        up=edge('xd.'+tag,.9,True);down=edge('xd.'+tag,.9,False)
        complete=len(up)==len(down)==len(rises[node])==len(falls[node])==18
        channel_swing=swing('xd.'+tag,18)
        if not complete:
            pulse_checks.append(dict(channel=tag,complete_pulses=False,passed=False));continue
        for k,at in enumerate(rises[node]):
            later=events[events>at];nxt=later[0] if len(later) else t[-1]
            armed=window('xd.'+tag+'reset',at-40,at-20,inclusive=True)
            held=window('xd.'+tag+'reset',down[k]+20,falls[node][k]-20)
            arm_min=float(armed.min()) if len(armed) else None;hold_max=float(held.max()) if len(held) else None
            ordered=bool(at<up[k]<down[k]<min(nxt,falls[node][k]))
            passed=bool(channel_swing and ordered and arm_min is not None and arm_min>=1.62
                        and hold_max is not None and hold_max<=.18)
            pulse_checks.append(dict(channel=tag,source_ps=float(at),complete_pulses=True,
                reset_armed_min_v=arm_min,reset_held_max_v=hold_max,nonempty_hold_window=bool(len(held)),passed=passed))
    pulse_ok=bool(len(pulse_checks)==36 and all(c['passed'] for c in pulse_checks))
    period=1e6/s['mhz'];half_error=period_error=slew_max=None
    if order_ok:
        low=q_up-q_down;high=q_down[1:]-q_up[:-1]
        half_error=float(max(abs(np.mean(low)-period/2),abs(np.mean(high)-period/2)))
        period_error=float(np.max(abs(q[2:]-q[:-2]-period)))
    output_swing=bool(swing('q',18))
    if output_swing:
        slew_max=float(max(np.max(edge('q',1.62,True)-edge('q',.18,True)),
                           np.max(edge('q',.18,False)-edge('q',1.62,False))))
    balanced=s['phase_error_ps']==0
    half_ok=bool(half_error is not None and half_error<=50) if balanced else None
    timing_ok=bool(output_swing and slew_max is not None and slew_max<=250
                   and period_error is not None and period_error<=20 and (not balanced or half_ok))
    supply=bool(np.max(abs(get('vdd')-1.8))<=1e-9)
    return dict(source_screen_passed=bool(source['input_contract_passed'] and event_ok and initial_ok and order_ok
            and pulse_ok and timing_ok and supply),input=source,event_checks=event_checks,pulse_checks=pulse_checks,
        event_integrity_passed=event_ok,initial_high_output_passed=initial_ok,alternating_output_order_passed=order_ok,
        pulse_generator_integrity_passed=pulse_ok,full_swing_output_passed=output_swing,
        maximum_output_slew_ps=slew_max,maximum_output_period_error_ps=period_error,
        mean_half_cycle_error_ps=half_error,balanced_half_cycle_required=balanced,symmetric_timing_passed=half_ok,
        timing_passed=timing_ok,fixed_supply_passed=supply,qualified_phy=False,physical_source_admitted=False,
        scope='All 36 source events and both complete final pulses only; full native stress, physical RC, loaded DLL and PHY remain required')
