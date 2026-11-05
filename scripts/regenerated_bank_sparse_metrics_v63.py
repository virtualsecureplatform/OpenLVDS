# SPDX-License-Identifier: GPL-3.0-only
"""Six-point native sparse admission; never a dense legal-code certificate."""
import math

CODES=((0,0),(0,1),(0,15),(0,16),(0,31),(1,0))


def compare(rows):
    points={}
    for row in rows:
        s=row['spec'];key=(s['coarse'],s['fine'])
        if key in points:raise ValueError('Duplicate sparse code')
        if key not in CODES:raise ValueError('Unexpected sparse code')
        r=row['result']
        if row.get('error') is not None or not r:raise ValueError('Incomplete native sparse result')
        for sample in r['samples']:
            if set(sample)!={'rise_delay_ps','fall_delay_ps'} or not all(math.isfinite(v) and v>0 for v in sample.values()):
                raise ValueError('Invalid sparse native delay')
        if len(r['samples'])!=2:raise ValueError('Require both complete native pulses')
        points[key]=r
    complete=set(points)==set(CODES);steps=[];overlap={}
    for edge in ('rise','fall'):
        def delay(c,f):return points[c,f]['samples'][1][edge+'_delay_ps']
        for a,b in ((0,1),(1,15),(15,16),(16,31)):
            if (0,a) not in points or (0,b) not in points:continue
            delta=delay(0,b)-delay(0,a)
            steps.append(dict(edge=edge,from_fine=a,to_fine=b,delay_change_ps=delta,
                              sampled_order_passed=delta>0,
                              adjacent_gap_passed=0<delta<=20 if b-a==1 else None))
        if (0,31) in points and (1,0) in points:overlap[edge+'_ps']=delay(0,31)-delay(1,0)
    voltage=bool(points) and all(r['terminal_screen_passed'] for r in points.values())
    controls=bool(points) and all(r['control_settling_passed'] for r in points.values())
    repeats=bool(points) and all(set(r['repeated_delay_difference_ps'])=={'rise','fall'} and
        all(math.isfinite(v) and 0<=v<=20 for v in r['repeated_delay_difference_ps'].values()) for r in points.values())
    headroom=points.get((0,0),{}).get('zero_code_fast_quarter_headroom_ps')
    quarter=headroom is not None and math.isfinite(headroom) and headroom>0
    fine=complete and all(s['sampled_order_passed'] and s['adjacent_gap_passed'] is not False for s in steps)
    coarse=len(overlap)==2 and all(v>0 for v in overlap.values())
    return dict(completed_sparse_points=len(points),all_sparse_points_present=complete,
        terminal_screen_passed=voltage,all_static_controls_passed=controls,repeated_pulses_passed=repeats,
        zero_code_fast_quarter_headroom_ps=headroom,zero_code_quarter_passed=quarter,
        fine_steps=steps,coarse_overlap=overlap,sampled_fine_order_and_adjacent_gaps_passed=fine,
        coarse_overlap_passed=coarse,sparse_native_screen_passed=bool(complete and voltage and controls and repeats and quarter and fine and coarse),
        whole_bank_rc_retained=True,dense_legal_code_coverage_proven=False,
        legal_code_table_admitted=False,electrical_qualification_passed=False,qualified_phy=False)
