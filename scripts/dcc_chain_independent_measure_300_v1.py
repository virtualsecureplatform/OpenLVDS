#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent raw-waveform reconstruction of combined chain and source DCCs."""
import numpy as np
from native_binary_raw_v2 import validate
from itertools import combinations
from dcc_independent_events_300_v1 import events
from dcc_independent_pulses_300_v1 import pulse_generator
import four_bank_native_measure_300_v1 as chain

VERSION='independent-source-dcc-four-section-native-measure-300-v1'


def measure(folder,observations,s):
    if set(observations)!={'sections','dcc'} or set(observations['dcc'])!={'0','1'}:
        raise ValueError('Require complete chain and both actual source DCC maps')
    result=chain.measure(folder,observations['sections'],s,independent_reader=True)
    column=lambda n:'v('+n.replace(':','.').lower()+')'
    required={column(n) for n in ('IN','OUT','B1_OUT','B2_OUT','DCC0_OUT','DCC1_OUT','DCC_RESET_N')}
    all_names=[d['name'] for o in list(observations['sections'].values())+list(observations['dcc'].values()) for d in o['devices']]
    if len(all_names)!=len(set(all_names)):raise ValueError('Colliding chain/DCC native device identities')
    for k,(a,b) in enumerate((('IN','B1_OUT'),('OUT','B2_OUT'))):
        o=observations['dcc'][str(k)]
        if o['input_nodes']!=[a,b] or o['output_node']!=f'DCC{k}_OUT' or not o['devices']:
            raise ValueError('Actual DCC phase connection or device map changed')
        required.update(column(n) for d in o['devices']+o['passive_resistors'] for n in d['terminals'] if n!='0')
    required.update(column(f'XDC{k}:{n}') for k in range(2) for n in ('a','b','areset','breset'))
    names,w=validate(folder/'bench.raw',required,s['stop_ns']*1e-9)
    index={n:k for k,n in enumerate(names)};t=w[:,index['time']]*1e12
    zero=np.zeros(len(t));get=lambda n:zero if n=='0' else w[:,index[column(n)]]
    reset=np.where(t<=1000,0,np.where(t>=1020,1.8,(t-1000)*.09));reset_error=float(np.max(np.abs(get('DCC_RESET_N')-reset)))
    rows={}
    for k in ('0','1'):
        o=observations['dcc'][k];timing=events(t,*[get(n) for n in o['input_nodes']],get(o['output_node']),s)
        stress=[]
        for d in o['devices']:
            v=[get(n) for n in d['terminals']]
            peak=max(float(np.max(np.abs(x-y))) for x,y in combinations(v,2))
            stress.append(dict(device=d['name'],maximum_terminal_difference_v=peak,limit_v=d['limit_v'],passed=bool(peak<=d['limit_v'])))
        pulse_checks={channel:pulse_generator(t,get(node),get(f'XDC{k}:{channel}'),get(f'XDC{k}:{channel}reset'),s)
            for channel,node in zip(('a','b'),o['input_nodes'])}
        pulse_passed=all(v['pulse_generator_integrity_passed'] for v in pulse_checks.values())
        passed=bool(pulse_passed and reset_error<=1e-9 and all(r['passed'] for r in stress) and all(timing[n] for n in (
            'one_transition_per_source_event_passed','full_swing_passed','output_slew_passed','period_screen_passed')))
        rows[k]=dict(timing=timing,terminal_stress=stress,terminal_screen_passed=all(r['passed'] for r in stress),
                     pulse_generators=pulse_checks,pulse_generator_integrity_passed=pulse_passed,
                     source_dcc_transport_passed=passed)
    return dict(chain=result,dcc=rows,maximum_reset_source_error_v=reset_error,
        combined_loading_transport_passed=bool(result['four_section_transport_passed'] and all(r['source_dcc_transport_passed'] for r in rows.values())),
        observed_mean_half_cycle_passed=all(r['timing']['observed_mean_half_cycle_passed'] for r in rows.values()),
        calibrated_phase_qualified=False,detector_fanout_qualified=False,shared_wire_rc_qualified=False,qualified_phy=False,
        scope='Startup-inclusive actual source-DCC/chain transport only; phase calibration, detector, routing and PHY remain required')
