#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exact linear-ramp eight-pulse entry stimulus; slew is explicitly 10–90%."""
import numpy as np

VERSION='eight-pulse-linear-entry-reference-300-v1'
REFERENCE_VOLTAGE_ERROR_V=1e-9
ROUNDING_PS=1e-6


def points(s):
    if (s['frequency_mhz'] not in (290,300,310) or s['duty'] not in (.4,.5,.6)
            or s['input_slew_ps'] not in (20,250) or s['cycles']!=8 or s['stop_ns']!=40):
        raise ValueError('Require the declared 300MHz entry-domain pulse protocol')
    period=1e6/s['frequency_mhz'];slew=s['input_slew_ps'];full=slew/.8
    result=[(0.,0.)]
    for k in range(8):
        rise=2100+k*period;fall=rise+s['duty']*period
        result.extend([(rise-full/2,0.),(rise-slew/2,.18),(rise,.9),
                       (rise+slew/2,1.62),(rise+full/2,1.8),
                       (fall-full/2,1.8),(fall-slew/2,1.62),(fall,.9),
                       (fall+slew/2,.18),(fall+full/2,0.)])
    result.append((40000.,0.))
    if any(b[0]<=a[0] for a,b in zip(result,result[1:])):
        raise ValueError('Entry pulse ramps overlap or exceed the complete transient')
    return result


def source(s):
    rows=['V_ENTRY IN 0 PWL(']
    for t,v in points(s):rows.append(f'+ {t:.17g}p {v:.17g}')
    return '\n'.join([*rows,'+ )'])


def evaluate(t,s):
    p=points(s)
    return np.interp(t,[x for x,v in p],[v for x,v in p])


def evaluate_independent(t,s):
    points(s)  # Same declared protocol, separate voltage reconstruction.
    value=np.zeros(len(t));period=1e6/s['frequency_mhz'];full=s['input_slew_ps']/.8
    for k in range(8):
        rise=2100+k*period;fall=rise+s['duty']*period
        up=np.clip((t-rise+full/2)/full,0,1)
        down=np.clip((fall+full/2-t)/full,0,1)
        value+=1.8*np.minimum(up,down)
    return value


GATES=('all_input_output_pulses_present','full_swing_pulses_passed',
       'measured_input_contract_passed','unwrapped_native_epoch_passed',
       'pulse_order_and_widths_passed','period_screen_passed','repeated_delay_screen_passed',
       'zero_code_quarter_passed','current_downstream_250ps_slew_domain_passed')


def apply_reference(result,t,vin,s,*,independent=False):
    """Apply only float-roundoff allowance to the verified ideal input ramp.

    Native-driven inputs, outputs, stress, history and quarter limits keep the
    original comparisons. All measured values remain unrounded and unclipped.
    """
    expected=(evaluate_independent if independent else evaluate)(t,s)
    error=float(np.max(np.abs(vin-expected)))
    step=float(np.max(np.diff(t)))
    valid=bool(error<=REFERENCE_VOLTAGE_ERROR_V and step<=2+ROUNDING_PS)
    bank=result['banks']['first'];r=bank['timing'];n=s['cycles']
    counts=all(row['input']==row['input_10_percent']==row['input_90_percent']==n
               for row in r['pulse_counts'].values())
    values=[v for group in r['input_slews_10_90_ps'].values() for v in group]
    domain=bool(valid and counts and len(values)==2*n
        and min(values)>=20-ROUNDING_PS and max(values)<=250+ROUNDING_PS
        and r['maximum_input_period_error_ps'] is not None and r['maximum_input_period_error_ps']<=20
        and r['input_timing_stimulus_passed'] is True)
    r.update(measured_input_contract_passed=domain,ideal_source_waveform_passed=valid,
             ideal_source_maximum_voltage_error_v=error,ideal_source_maximum_sample_step_ps=step,
             ideal_source_declared_10_90_ps=s['input_slew_ps'],ideal_source_roundoff_allowance_ps=ROUNDING_PS)
    r['stage_transport_passed']=bool(all(r[k] for k in GATES) and r['input_timing_stimulus_passed'] is True and valid)
    bank['bank_screen_passed']=bool(r['stage_transport_passed'] and bank['terminal_screen_passed']
        and bank['control_settling_passed'] and all(c['passed'] for c in bank['external_controls']))
    result['entry_reference_waveform']=VERSION
    result['two_bank_zero_pilot_passed']=bool(result['fixed_supply_passed'] and
        all(b['bank_screen_passed'] for b in result['banks'].values()))
    return result
