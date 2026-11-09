#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure the complete corrected DCC input contract, never DCC admission."""
import numpy as np
import dcc_input_waveforms_300_v2 as reference
from regenerated_bank_periodic_measure_v67 import crossings


def edge_times(t,v,level,up,independent):
    if not independent:return np.asarray(crossings(t,v,level,up))
    state=v>=level;indices=np.flatnonzero((~state[:-1]&state[1:]) if up else (state[:-1]&~state[1:]))
    return t[indices]+(level-v[indices])*(t[indices+1]-t[indices])/(v[indices+1]-v[indices])


def measure(names,w,s,*,independent=False):
    reference.check(s)
    required={'time','v(p0)','v(p180)'}
    if len(names)!=len(set(names)) or not required<=set(names) or w.ndim!=2 or w.shape[1]!=len(names):
        raise ValueError('Missing complete DCC input vectors')
    if not len(w) or not np.isfinite(w).all():raise ValueError('Require finite complete native DCC input trace')
    t=w[:,names.index('time')]*1e12;stop=reference.capture_stop_ps(s)
    if abs(t[0])>1e-6 or t[-1]<stop-1e-6 or np.any(np.diff(t)<=0):
        raise ValueError('Require complete native DCC input trace including DC and final tail')
    if len(t)<2:raise ValueError('Insufficient complete native DCC input trace')
    max_step=float(np.max(np.diff(t)));clock={};rising={};period=1e6/s['mhz']
    for phase,key in (('P0','r'),('P180','f')):
        value=w[:,names.index('v('+phase.lower()+')')]
        ideal=reference.evaluate(t,s,phase,independent=independent)
        voltage_error=float(np.max(np.abs(value-ideal)))
        edges={(up,level):edge_times(t,value,level,up,independent) for up in (True,False) for level in (.18,.9,1.62)}
        counts={('rise' if up else 'fall')+'_'+str(level):len(v) for (up,level),v in edges.items()}
        count_ok=all(n==18 for n in counts.values());rising[phase]=edges[True,.9]
        epoch_error=slew_error=width_error=period_error=None;rise_slew=[];fall_slew=[];widths=[]
        if count_ok:
            _,first,high,full=reference.parameters(s,phase)
            expected=first+np.arange(18)*period
            epoch_error=float(max(np.max(abs(edges[True,.9]-expected)),np.max(abs(edges[False,.9]-expected-high))))
            rise_slew=(edges[True,1.62]-edges[True,.18]).tolist()
            fall_slew=(edges[False,.18]-edges[False,1.62]).tolist()
            widths=(edges[False,.9]-edges[True,.9]).tolist()
            slew_error=float(np.max(np.abs(np.r_[rise_slew,fall_slew]-s[key+'_slew_10_90_ps'])))
            width_error=float(np.max(abs(np.asarray(widths)-high)))
            period_error=float(max(np.max(abs(np.diff(edges[True,.9])-period)),np.max(abs(np.diff(edges[False,.9])-period))))
        passed=bool(count_ok and voltage_error<=1e-9 and epoch_error<=.02 and slew_error<=1e-6
                    and width_error<=.02 and period_error<=.02)
        clock[phase]=dict(counts=counts,all_startup_edges_present=count_ok,
            maximum_ideal_voltage_error_v=voltage_error,maximum_epoch_error_ps=epoch_error,
            maximum_slew_error_ps=slew_error,maximum_high_width_error_ps=width_error,
            maximum_period_error_ps=period_error,rising_slews_ps=rise_slew,falling_slews_ps=fall_slew,
            high_widths_ps=widths,passed=passed)
    spacing=None
    if all(len(v)==18 for v in rising.values()):
        spacing=float(np.max(abs(rising['P180']-rising['P0']-period/2-s['phase_error_ps'])))
    phase_ok=spacing is not None and spacing<=.02
    return dict(input_contract_passed=bool(all(v['passed'] for v in clock.values()) and phase_ok and max_step<=1+1e-6),
        clocks=clock,phase_spacing_passed=bool(phase_ok),maximum_phase_spacing_error_ps=spacing,
        maximum_sample_step_ps=max_step,complete_trace_verified=True,qualified_phy=False,dcc_source_admitted=False,
        scope='Complete input-waveform contract only; DCC event, reset, output timing, stress and physical qualification remain required')
