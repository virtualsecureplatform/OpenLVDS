# SPDX-License-Identifier: GPL-3.0-only
"""Full routed-DCC startup, positive phase-zero delivery and native MOS screen."""
import itertools
import numpy as np
import dcc_input_measure_300_v2 as inputs
import routed_dcc_fixture_300_v1 as fixture


def measure(names,w,s,obs,*,independent=False):
    if len(obs['devices'])!=192 or len(obs['passive_resistors'])!=4:
        raise ValueError('Incomplete routed DCC native map')
    canonical=lambda n:'v('+n.replace(':','.').lower()+')'
    required={'v(p0)','v(p180)','v(q)','v(vdd)','v(reset_n)'}
    required.update(canonical(n) for n in obs['signals'].values())
    required.update(canonical(n) for d in obs['devices']+obs['passive_resistors'] for n in d['terminals'] if n!='0')
    if len({d['name'] for d in obs['devices']+obs['passive_resistors']})!=196 or not required<=set(names):
        raise ValueError('Missing or duplicated routed DCC terminal observations')
    source=inputs.measure(names,w,s,independent=independent)
    index={n:k for k,n in enumerate(names)};t=w[:,index['time']]*1e12
    def get(n):return np.zeros(len(t)) if n=='0' else w[:,index[canonical(n)]]
    def edge(n,level=.9,up=True):return inputs.edge_times(t,get(n),level,up,independent)
    def window(n,a,b):
        v=get(n)
        if independent:return v[np.searchsorted(t,a,side='left'):np.searchsorted(t,b,side='right')]
        return v[(t>=a)&(t<=b)]
    release=fixture.release_ps(s)
    if obs['release_50_ps']!=release or obs['expected_first_active_phase']!='P180' or obs['expected_output_rising_phase']!='P0':
        raise ValueError('Routed DCC release contract changed')
    reset_error=float(np.max(np.abs(get('RESET_N')-1.8*np.clip((t-release+10)/20,0,1))))
    reset_edges=edge('RESET_N');reset_ok=bool(reset_error<=1e-9 and len(reset_edges)==1 and abs(reset_edges[0]-release)<=.02)
    rises={n:edge(n) for n in ('P0','P180')};falls={n:edge(n,up=False) for n in ('P0','P180')}
    events=sorted((float(a),n) for n,v in rises.items() for a in v if a>release)
    expected_counts={'P0':14,'P180':15}
    active_ok=bool(len(events)==29 and events[0][1]=='P180'
        and all(sum(n==phase for a,n in events)==count for phase,count in expected_counts.items()))
    q_up=edge('Q');q_down=edge('Q',up=False);q=np.sort(np.r_[q_up,q_down])
    ev=edge(obs['signals']['events']);ev=ev[ev>release]
    checks=[]
    for k,(at,phase) in enumerate(events):
        end=events[k+1][0] if k+1<len(events) else t[-1]
        pulse=ev[(ev>at)&(ev<end)];output=q[(q>at)&(q<end)]
        direction=q_up if phase=='P0' else q_down
        proper=direction[(direction>at)&(direction<end)]
        checks.append(dict(source_ps=at,phase=phase,event_count=len(pulse),output_count=len(output),
            correct_direction_count=len(proper),passed=bool(len(pulse)==len(output)==len(proper)==1)))
    event_ok=bool(active_ok and len(ev)==len(q)==29 and len(q_up)==14 and len(q_down)==15 and all(c['passed'] for c in checks))
    # Initial output may begin changing during the first active input ramp.
    quiet_end=(events[0][0]-fixture.waveform.parameters(s,events[0][1])[3]/2) if events else release
    quiet=window('Q',0,quiet_end);startup=bool(len(quiet) and quiet.min()>=1.62)
    def swing(n,up_count,down_count,after):
        return all(len(edge(n,level,up)[edge(n,level,up)>after])==count
                   for level in (.18,.9,1.62) for up,count in ((True,up_count),(False,down_count)))
    output_swing=swing('Q',14,15,0)
    event_swing=swing(obs['signals']['events'],29,29,release)
    pulse_checks=[]
    for phase,pulse_tag,clear_tag in (('P0','pulse0','clear0'),('P180','pulse180','clear180')):
        pulse=obs['signals'][pulse_tag];clear=obs['signals'][clear_tag]
        up=edge(pulse);up=up[up>release];down=edge(pulse,up=False);down=down[down>release]
        active=rises[phase][rises[phase]>release];count=expected_counts[phase]
        complete=len(up)==len(down)==len(active)==count
        full=swing(pulse,count,count,release)
        if not complete:
            pulse_checks.append(dict(phase=phase,complete_pulses=False,rises=len(up),falls=len(down),passed=False));continue
        for k,at in enumerate(active):
            following=[a for a,n in events if a>at];next_event=following[0] if following else t[-1]
            falling=falls[phase][falls[phase]>at];end=float(falling[0]) if len(falling) else at
            armed=window(clear,at-40,at-20);held=window(clear,down[k]+20,end-20) if end-20>down[k]+20 else np.array([])
            arm=float(armed.min()) if len(armed) else None;hold=float(held.max()) if len(held) else None
            passed=bool(full and at<up[k]<down[k]<min(next_event,end) and arm is not None and arm>=1.62 and hold is not None and hold<=.18)
            pulse_checks.append(dict(phase=phase,source_ps=float(at),complete_pulses=True,
                reset_armed_min_v=arm,reset_held_max_v=hold,nonempty_hold_window=bool(len(held)),passed=passed))
    pulse_ok=bool(len(pulse_checks)==29 and all(c['passed'] for c in pulse_checks))
    slew=period_error=half_error=None
    if len(q_up)==14 and len(q_down)==15:
        period=1e6/s['mhz'];low=q_up-q_down[:-1];high=q_down[1:]-q_up
        half_error=float(max(abs(low.mean()-period/2),abs(high.mean()-period/2)))
        period_error=float(np.max(np.abs(q[2:]-q[:-2]-period)))
    if output_swing:
        slew=float(max(np.max(edge('Q',1.62)-edge('Q',.18)),np.max(edge('Q',.18,False)-edge('Q',1.62,False))))
    balanced=s['phase_error_ps']==0
    timing=bool(output_swing and slew is not None and slew<=250 and period_error is not None and period_error<=20
                and half_error is not None and (not balanced or half_error<=50))
    stress=[]
    for d in obs['devices']:
        if d['limit_v']!=1.95 or '01v8' not in d['model'] or len(d['terminals'])!=4:raise ValueError('Routed DCC voltage domain changed')
        values=[get(n) for n in d['terminals']]
        maximum=(max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2)) if independent
                 else float(np.max(np.ptp(np.stack(values),axis=0))))
        stress.append(dict(device=d['name'],maximum_terminal_span_v=maximum,limit_v=1.95,passed=maximum<=1.95))
    stress_ok=all(d['passed'] for d in stress);supply=bool(np.max(np.abs(get('VDD')-1.8))<=1e-9)
    phase0=bool(event_ok and startup and output_swing)
    return dict(input=source,reset_input_contract_passed=reset_ok,maximum_reset_input_error_v=reset_error,
        complete_active_input_events_passed=active_ok,event_checks=checks,event_integrity_passed=event_ok,
        initial_high_output_passed=startup,phase0_delivery_passed=phase0,pulse_checks=pulse_checks,
        pulse_generator_integrity_passed=pulse_ok,event_full_swing_passed=event_swing,output_full_swing_passed=output_swing,
        maximum_output_slew_ps=slew,maximum_output_period_error_ps=period_error,mean_half_cycle_error_ps=half_error,
        balanced_half_cycle_required=balanced,timing_passed=timing,terminal_stress=stress,
        native_terminal_stress_passed=stress_ok,fixed_supply_passed=supply,
        routed_point_passed=bool(source['input_contract_passed'] and reset_ok and phase0 and event_swing and pulse_ok and timing and stress_ok and supply),
        actual_release_circuit_qualified=False,loaded_dll_admitted=False,qualified_phy=False,
        scope='Single retained routed macro with ideal phase sources and scheduled reset only; no actual release circuit, full PVT, loaded DLL or PHY admission')
