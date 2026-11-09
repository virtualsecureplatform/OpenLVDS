# SPDX-License-Identifier: GPL-3.0-only
"""Corrected-input DCC events plus complete source-MOS stress from native DC."""
import itertools
import numpy as np
import dcc_source_measure_300_v2 as source

VERSION='complete-native-source-dcc-health-300-v3'


def measure(names,w,s,observations,*,independent=False):
    if (len(observations['devices'])!=136 or len(observations['passive_resistors'])!=2
            or len({d['name'] for d in observations['devices']+observations['passive_resistors']})!=138):
        raise ValueError('Incomplete or duplicate source DCC observations')
    wanted={'v(reset_n)'}
    canonical=lambda n:'v('+n.lower().replace(':','.')+')'
    for d in observations['devices']:
        if d['limit_v']!=1.95 or '01v8' not in d['model'] or len(d['terminals'])!=4:
            raise ValueError('Native DCC voltage domain changed')
    for d in observations['devices']+observations['passive_resistors']:
        wanted.update(canonical(n) for n in d['terminals'] if n!='0')
    if not wanted<=set(names):raise ValueError('Missing actual source DCC terminal voltage')
    original=source.measure(names,w,s,independent=independent)
    index={n:k for k,n in enumerate(names)};t=w[:,index['time']]*1e12
    def get(n):return np.zeros(len(t)) if n=='0' else w[:,index[canonical(n)]]
    reset_error=float(np.max(np.abs(get('RESET_N')-1.8*np.clip((t-1000)/20,0,1))))
    reset_ok=reset_error<=1e-9
    stress=[]
    for d in observations['devices']:
        v=[get(n) for n in d['terminals']]
        maximum=(max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(v,2)) if independent
                 else float(np.max(np.ptp(np.stack(v),axis=0))))
        stress.append(dict(device=d['name'],maximum_terminal_span_v=maximum,limit_v=1.95,passed=maximum<=1.95))
    passed=all(d['passed'] for d in stress)
    return dict(source=original,reset_input_contract_passed=reset_ok,maximum_reset_input_error_v=reset_error,
        native_mos=136,passive_resistors=2,terminal_stress=stress,native_terminal_stress_passed=passed,
        source_screen_passed=bool(original['source_screen_passed'] and reset_ok and passed),
        physical_source_admitted=False,complete_matrix_admitted=False,qualified_phy=False,
        scope='Complete corrected-input source-DCC timing/reset and all 136 source-MOS envelopes only; no physical RC, loaded DLL or PHY admission')
