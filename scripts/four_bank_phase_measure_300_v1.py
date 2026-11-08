#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Unwrapped phase-grid diagnostics; transport does not imply calibrated phase."""
from regenerated_bank_periodic_measure_v67 import crossings

NODES=('IN','OUT','B1_OUT','B2_OUT','B3_OUT')


def measure(t,get,s):
    period=1e6/s['frequency_mhz'];count=s['cycles'];rows={};complete=True
    for up,edge in ((True,'rise'),(False,'fall')):
        events=[crossings(t,get(node),.9,up) for node in NODES]
        counts={node:len(v) for node,v in zip(NODES,events)}
        full=all(v==count for v in counts.values());complete=complete and full
        offsets={};sections={};errors={};spreads=[];closure=[]
        if full:
            for k in range(1,5):
                offsets[NODES[k]]=[b-a for a,b in zip(events[0],events[k])]
                sections[str(k-1)]=[b-a for a,b in zip(events[k-1],events[k])]
                errors[NODES[k]]=[v-k*period/4 for v in offsets[NODES[k]]]
            spreads=[max(values)-min(values) for values in zip(*sections.values())]
            closure=[v-period for v in offsets['B3_OUT']]
        rows[edge]=dict(pulse_counts=counts,complete_events=full,unwrapped_phase_offsets_ps=offsets,
            section_delays_ps=sections,phase_grid_errors_ps=errors,section_delay_spreads_ps=spreads,
            full_period_closure_errors_ps=closure,
            positive_ordered_transport=bool(full and all(v>0 for values in sections.values() for v in values)),
            maximum_phase_grid_error_ps=max((abs(v) for values in errors.values() for v in values),default=None),
            maximum_full_period_closure_error_ps=max((abs(v) for v in closure),default=None))
    grid=bool(complete and all(r['positive_ordered_transport'] and r['maximum_phase_grid_error_ps']<=50 for r in rows.values()))
    closure=bool(complete and all(r['maximum_full_period_closure_error_ps']<=20 for r in rows.values()))
    return dict(edges=rows,all_startup_events_present=bool(complete),
        observed_50ps_phase_grid_passed=grid,observed_20ps_period_closure_passed=closure,
        calibrated_phase_qualified=False,qualified_phy=False,
        scope='Direct unwrapped native phase errors only; no calibration, detector, physical or PHY admission')
