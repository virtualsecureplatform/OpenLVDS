#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh seven-cycle counter protocol at 290/300/310 MHz; no waveform rescaling."""
import itertools
import numpy as np
import clocking_profile_300 as policy
import probe_local_setter_shared_rc_v351 as pilot
import analyze_counter_low_windows_v305 as diagnosis
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import crossings

STOP_NS = 40
REQUEST = 'VREQUEST REQUEST 0 PWL(0 0 3.39n 0 3.41n 1.8 27.99n 1.8 28.01n 0 31.99n 0 32.01n 1.8)'


def fixture(folder, spec, devices):
    if spec['mhz'] not in policy.load()['requirements']['clock_test_mhz']:
        raise ValueError('Only fresh 300 MHz profile clocks are allowed')
    text = pilot.fixture(folder, spec, devices)
    old = 'VREQUEST REQUEST 0 PWL(0 0 3.39n 0 3.41n 1.8 20.99n 1.8 21.01n 0 22.99n 0 23.01n 1.8)'
    if text.count(old) != 1 or text.count('.tran 1p 26n 0 1p') != 1:
        raise ValueError('Original counter protocol changed')
    return text.replace(old, REQUEST, 1).replace('.tran 1p 26n 0 1p', '.tran 1p 40n 0 1p', 1)


def timing(t, get, spec):
    """Measure actual native event times and fixed stopped-clock observation windows."""
    if t[0] > .001 or t[-1] < 39999 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Require full finite 40 ns native trace')
    edge = lambda node, up=True: crossings(t, get(node), up)
    request, drop, clk = edge('REQUEST'), edge('REQUEST', False), edge('CLK')
    raw = edge('RCLK'); raw_falls = edge('RCLK', False)
    if (len(request) != 2 or len(drop) != 1 or len(clk) != 7 or len(raw) != 7
            or len(raw_falls) != 6+(spec['stop_level'] == 0)
            or max(abs(np.diff(raw)-1e6/spec['mhz'])) > .01
            or max(abs(request-np.array([3400.,32000.]))) > .01 or abs(drop[0]-28000) > .01):
        raise ValueError('Incomplete or wrong fresh counter stimulus/clock epochs')
    expected_raw=2050+np.arange(7)*1e6/spec['mhz']
    expected_falls=expected_raw[:len(raw_falls)]+spec['duty']*1e6/spec['mhz']
    if (np.max(abs(raw-expected_raw))>.01 or np.max(abs(raw_falls-expected_falls))>.01
            or np.any(clk-raw<=0) or np.any(clk-raw>=500000/spec['mhz'])):
        raise ValueError('Wrong raw duty or noncausal buffered clock epoch')
    prep, release = edge('PREPARE'), edge('RESET_N')
    if len(prep) != 1 or len(release) != 1:
        raise ValueError('Wrong public counter rising-event count')
    counts = {}; latencies = {}
    for name, event in (('prepare', prep[0]), ('public_release', release[0])):
        prior = clk[(clk > request[0]) & (clk < event)]
        counts[name] = len(prior)
        latencies[name] = float(event-prior[-1]) if len(prior) else None
    # Last possible raw transition is <24.86 ns at 290 MHz/60% duty.
    if np.max(np.abs(get('CLK')[t >= 27000]-1.8*spec['stop_level'])) > .18:
        raise ValueError('Clock not stopped before asynchronous REQUEST clear')
    held = all(np.max(np.abs(get(n)[t < request[0]])) <= .18 for n in ('PREPARE','RESET_N'))
    clear = all(np.max(np.abs(get(n)[t >= 30000])) <= .18 for n in ('PREPARE','RESET_N'))
    for n in ('PREPARE','RESET_N'):
        falls = edge(n, False)
        clear = clear and len(falls) == 1 and drop[0] < falls[0] < request[1]
    internal, internal_falls = edge('XD:XR:request_i'), edge('XD:XR:request_i', False)
    if len(internal) != 2 or len(internal_falls) != 1 or np.any(internal-request <= 0):
        raise ValueError('Wrong or noncausal buffered REQUEST events')
    events = {n: edge('XD:XR:'+n) for n in ('low0','high1','low1','armed')}
    if any(len(events[n]) != expected for n, expected in
           (('low0',1+(spec['stop_level']==0)),('high1',1),('low1',1),('armed',1))):
        raise ValueError('Wrong intermediate phase-state event count')
    ordered = bool(events['low0'][0] < clk[1] < events['high1'][0] < events['low1'][0] < clk[2] < prep[0])
    phase = bool(prep[0] < events['armed'][0] < clk[3] < release[0])
    for n in ('low0','low1','armed'):
        phase = phase and np.interp(events[n][0],t,get('CLK')) < .18
    phase_clear = {n: bool(np.max(np.abs(get('XD:XR:'+n)[t >= 30000])) <= .18)
                   for n in ('high1','low1','armed')}
    window = diagnosis.windows(t, {'CLK':get('CLK'), **{n:get('XD:XR:'+n) for n in diagnosis.STAGES}})
    half = 500000/spec['mhz']
    timely = all(v is not None and 0 < v < half for v in latencies.values())
    passed = bool(held and clear and counts == dict(prepare=2,public_release=3) and timely
                  and ordered and phase and all(phase_clear.values())
                  and window['all_three_assertions_in_original_low_windows'])
    values = {n:float(np.interp(events[n][0],t,get('CLK'))) for n in diagnosis.STAGES}
    return dict(prepare_time_ps=float(prep[0]),public_release_time_ps=float(release[0]),
        clock_edges_before_transition=counts,latency_from_qualifying_clock_ps=latencies,
        margin_to_next_half_phase_ps={k:half-v if v is not None else None for k,v in latencies.items()},
        held_before_request_passed=bool(held),stopped_clock_clear_and_reassert_passed=bool(clear),
        buffered_request_rise_delays_ps=(internal-request).tolist(),
        intermediate_phase_events_ps={n:events[n].tolist() for n in ('low0','high1','low1')},
        arm_time_ps=float(events['armed'][0]),phase_arming_passed=bool(phase),
        stopped_clock_arm_clear_passed=phase_clear['armed'],alternating_phase_order_passed=ordered,
        stopped_clock_intermediate_clear_passed=phase_clear['high1'] and phase_clear['low1'],
        low_windows=window,clock_at_low_phase_assertion_v=values,
        minimum_clock_low_voltage_margin_v=.18-max(values.values()),
        timing_protocol_passed=passed,protocol_stop_ns=40)


def measure(folder, identity, spec):
    devices=identity['devices'][pilot.VARIANT]
    signals=['CLK','RCLK','REQUEST','PREPARE','RESET_N',
             *['XD:XR:'+n for n in ('request_i','low0','high1','low1','armed')]]
    nodes=set(signals)|{n for d in devices for n in d['terminals'] if n!='0'}
    col=lambda n:'v('+n.replace(':','.').lower()+')'
    names,w=validate(folder/'bench.raw',{col(n) for n in nodes},40e-9)
    idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12;zero=np.zeros(len(t))
    get=lambda n:zero if n=='0' else w[:,idx[col(n)]]
    result=timing(t,get,spec);stress=[]
    if len(devices)!=808 or len({d['name'] for d in devices})!=808:
        raise ValueError('Require complete 808-MOS actual loaded counter')
    for d in devices:
        values=[get(n) for n in d['terminals']]
        peak=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2))
        stress.append(dict(device=d['name'],max_terminal_difference_v=peak,
                           limit_v=d['limit_v'],passed=peak<=d['limit_v']))
    passed=bool(result['timing_protocol_passed'] and all(d['passed'] for d in stress))
    return dict(result,terminal_stress=stress,terminal_screen_passed=all(d['passed'] for d in stress),
                counter_feasibility_passed=passed,hypothesis_point_checks_passed=passed,
                component_rc_only=False,counter_shared_wire_rc_qualified=True,
                whole_clock_rc_qualified=False,all_pvt_covered=False,
                electrical_qualification_passed=False,qualified_phy=False)
