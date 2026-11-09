# SPDX-License-Identifier: GPL-3.0-only
"""Decompose all source-DCC event latencies without discarding startup epochs."""
import numpy as np
import dcc_source_measure_300_v2 as source

STAGES=('source_to_pulse','pulse_to_or','or_to_toggle','toggle_to_output')


def measure(names,w,s,*,independent=False):
    original=source.measure(names,w,s,independent=independent)
    if not original['input']['input_contract_passed'] or not all(original[k] for k in ('event_integrity_passed','initial_high_output_passed',
        'alternating_output_order_passed','pulse_generator_integrity_passed','full_swing_output_passed')):
        raise ValueError('Require complete source events and pulse/reset integrity for path analysis')
    if 'v(xd.qt)' not in names:raise ValueError('Missing actual toggle-FF output')
    t=w[:,names.index('time')]*1e12
    def edge(n,up=True):
        return source.inputs.edge_times(t,w[:,names.index('v('+n+')')],.9,up,independent)
    events=sorted((float(x),phase) for phase,node in (('P0','p0'),('P180','p180')) for x in edge(node))
    data={phase:{n:[] for n in ('source','pulse','or','toggle','output')} for phase in ('P0','P180')}
    for k,(at,phase) in enumerate(events):
        end=events[k+1][0] if k+1<len(events) else t[-1]
        nodes=(('pulse','xd.a' if phase=='P0' else 'xd.b',True),('or','xd.events',True),
               ('toggle','xd.qt',phase=='P0'),('output','q',phase=='P180'))
        data[phase]['source'].append(at)
        for label,node,up in nodes:
            all_edges=edge(node,up);selected=all_edges[(all_edges>at)&(all_edges<end)]
            if len(selected)!=1:raise ValueError('Missing/extra native path event: '+node)
            data[phase][label].append(float(selected[0]))
    profiles={}
    for phase,row in data.items():
        if any(len(v)!=18 for v in row.values()):raise ValueError('Require every startup-inclusive path epoch')
        a={k:np.asarray(v) for k,v in row.items()}
        stages={k:(a[right]-a[left]).tolist() for k,left,right in zip(STAGES,
            ('source','pulse','or','toggle'),('pulse','or','toggle','output'))}
        total=a['output']-a['source'];reconstructed=sum(np.asarray(v) for v in stages.values())
        residual=float(np.max(np.abs(total-reconstructed)))
        if residual>1e-6:raise ValueError('Native path decomposition does not close')
        profiles[phase]=dict(event_epochs_ps=row,stage_delays_ps=stages,source_to_output_ps=total.tolist(),
            mean_stage_delays_ps={k:float(np.mean(v)) for k,v in stages.items()},maximum_path_sum_residual_ps=residual)
    period=1e6/s['mhz'];r=np.asarray(data['P0']['output']);f=np.asarray(data['P180']['output'])
    low=float(np.mean(f-r-period/2));high=float(np.mean(r[1:]-f[:-1]-period/2))
    reconstructed=max(abs(low),abs(high))
    if abs(reconstructed-original['mean_half_cycle_error_ps'])>1e-6:
        raise ValueError('Stage paths do not reproduce the native half-cycle error')
    differences={k:profiles['P180']['mean_stage_delays_ps'][k]-profiles['P0']['mean_stage_delays_ps'][k] for k in STAGES}
    spacing=float(np.mean(np.asarray(data['P180']['source'])-data['P0']['source']-period/2))
    if abs(sum(differences.values())+spacing-low)>1e-6:raise ValueError('Signed half-cycle stage accounting does not close')
    return dict(paths=profiles,mean_phase180_minus_phase0_stage_ps=differences,
        mean_input_half_spacing_error_ps=spacing,mean_low_interval_error_ps=low,mean_high_interval_error_ps=high,
        reconstructed_mean_half_cycle_error_ps=reconstructed,original_source_screen_passed=original['source_screen_passed'],
        first_captured_phase='P0',output_rising_phase='P180',timing_modified=False,qualified_phy=False,
        scope='Observed source path timing only; source classifications preserved; no routed phase-zero, architecture, matrix or PHY admission')
