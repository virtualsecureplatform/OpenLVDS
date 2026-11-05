# SPDX-License-Identifier: GPL-3.0-only
"""Native SS40 fine-code curve for two coarse selections; no all-PVT ROM."""
import math
import regenerated_bank_sparse_metrics_v63 as sparse

CODES=tuple((c,f) for c in (0,1) for f in range(32))
FRESH_CODES=tuple(code for code in CODES if code not in sparse.CODES)


def compare(rows):
    points={}
    for row in rows:
        s=row['spec'];code=(s['coarse'],s['fine']);r=row['result']
        if code in points:raise ValueError('Duplicate dense code')
        if code not in CODES:raise ValueError('Unexpected dense code')
        if row.get('error') is not None or not r:raise ValueError('Incomplete dense native result')
        if len(r['samples'])!=2:raise ValueError('Require two complete dense pulses')
        for sample in r['samples']:
            if set(sample)!={'rise_delay_ps','fall_delay_ps'} or not all(math.isfinite(v) and v>0 for v in sample.values()):
                raise ValueError('Invalid dense native delay')
        points[code]=r
    base=sparse.compare([r for r in rows if (r['spec']['coarse'],r['spec']['fine']) in sparse.CODES])
    complete=set(points)==set(CODES);steps=[]
    for c in (0,1):
        for a in range(31):
            if (c,a) not in points or (c,a+1) not in points:continue
            for edge in ('rise','fall'):
                delta=points[c,a+1]['samples'][1][edge+'_delay_ps']-points[c,a]['samples'][1][edge+'_delay_ps']
                steps.append(dict(coarse=c,from_fine=a,to_fine=a+1,edge=edge,delay_change_ps=delta,
                                  monotonic_adjacent_gap_passed=0<delta<=20))
    voltage=bool(points) and all(r['terminal_screen_passed'] for r in points.values())
    controls=bool(points) and all(r['control_settling_passed'] for r in points.values())
    repeat=bool(points) and all(set(r['repeated_delay_difference_ps'])=={'rise','fall'} and
        all(math.isfinite(v) and 0<=v<=20 for v in r['repeated_delay_difference_ps'].values()) for r in points.values())
    fine=complete and len(steps)==124 and all(s['monotonic_adjacent_gap_passed'] for s in steps)
    return dict(completed_dense_points=len(points),all_64_fine_points_present=complete,
        terminal_screen_passed=voltage,all_static_controls_passed=controls,repeated_pulses_passed=repeat,
        inherited_sparse_comparison=base,dense_fine_steps=steps,all_adjacent_fine_gaps_passed=fine,
        ss40_dense_fine_screen_passed=bool(complete and voltage and controls and repeat and fine and base['sparse_native_screen_passed']),
        whole_bank_rc_retained=True,all_pvt_covered=False,full_coarse_range_covered=False,
        dense_legal_code_coverage_proven=False,legal_code_table_admitted=False,
        electrical_qualification_passed=False,qualified_phy=False)
