#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Find a common conservative delay ordering; proposals never admit a PHY.

Input intervals must eventually come from separately admitted complete native
characterization. Synthetic intervals exercise this selector only. A common
code sequence may interleave raw coarse/fine codes; update safety is separate.
"""
from bisect import bisect_right
from dataclasses import asdict
import json
from pathlib import Path
from clocking_v2 import Delay,common_legal_codes

ROOT=Path(__file__).resolve().parents[1]
PVT=tuple(f'{p}:{t}' for p in ('tt','ff','ss','fs','sf') for t in (0,25,40))


def policy(mode,coarse_count,fine_count):
    spec=json.loads((ROOT/'clocking_v2.json').read_text());req=json.loads((ROOT/'requirements.json').read_text());search=spec['search']
    if (mode not in ('tx','rx') or type(coarse_count) is not int or type(fine_count) is not int
        or coarse_count not in search[mode+'_coarse_counts'] or fine_count not in search['fine_counts']
        or req['clock_test_mhz']!=[390,400,410] or req['temperatures_c']!=[0,25,40]
        or set(req['process_corners'])!={'tt','ff','ss','fs','sf'}
        or search['maximum_legal_gap_ps']!=20 or search['fine_step_target_ps']!=10 or search['rx_extra_range_ps']!=500):
        raise ValueError('Require approved TX/RX dimensions, fifteen PVT and unchanged delay-gap policy')
    return dict(mode=mode,coarse_count=coarse_count,fine_count=fine_count,
        target_gap_ps=10.,maximum_gap_ps=20.,
        quarter_min_ps=1e6/max(req['clock_test_mhz'])/4,
        quarter_max_ps=1e6/min(req['clock_test_mhz'])/4,
        rx_span_ps=1e6/min(req['clock_test_mhz'])+search['rx_extra_range_ps'])


def vectors(corners,coarse_count,fine_count):
    if set(corners)!=set(PVT):raise ValueError('Require exactly all fifteen process/temperature points')
    codes=set(range(coarse_count*fine_count));ordered=[]
    for corner in PVT:
        if set(corners[corner])!={'rise','fall'}:raise ValueError('Require both characterized edges at every PVT')
        for edge in ('rise','fall'):
            table=corners[corner][edge]
            if (len(table)!=len(codes) or any(not isinstance(d,Delay) for d in table)
                or {d.code for d in table}!=codes):raise ValueError('Require complete unique raw coarse/fine coverage at every PVT and edge')
            # Delay validates finite conservative intervals; input list order has no meaning.
            ordered.append({d.code:d for d in table})
    return {code:tuple(table[code] for table in ordered) for code in sorted(codes)}


def graph(points,gap):
    """Universal interval order is acyclic in any reference dimension.

    Bisect bounds avoid comparing distant raw codes. Candidate edges must
    satisfy strict monotonicity and the largest possible gap in every dimension.
    """
    codes=sorted(points,key=lambda c:(points[c][0].lo_ps,c));lows=[points[c][0].lo_ps for c in codes];edges=[]
    for left in codes:
        a=points[left];start=bisect_right(lows,a[0].hi_ps);end=bisect_right(lows,a[0].lo_ps+gap)
        edges.append([j for j in range(start,end) if all(b.lo_ps>x.hi_ps and b.hi_ps-x.lo_ps<=gap for x,b in zip(a,points[codes[j]]))])
    return codes,edges


def find_path(points,gap,mode,quarter_min=0.,quarter_max=0.,rx_span=0.):
    """Complete DAG reachability with nondominated start-interval labels.

    At the same end node, a start whose upper bounds are no larger in every
    dimension can cover at least as much conservative range. It dominates
    later starts regardless of how the end was reached. Parent labels retain
    real edge-by-edge witnesses; no greedy one-corner ordering is assumed.
    """
    codes,edges=graph(points,gap);labels=[];at=[[] for _ in codes]
    upper={c:tuple(d.hi_ps for d in points[c]) for c in codes}
    def dominates(a,b):return all(x<=y for x,y in zip(upper[a],upper[b]))
    def insert(node,start,parent):
        if any(dominates(labels[k][1],start) for k in at[node]):return
        at[node]=[k for k in at[node] if not dominates(start,labels[k][1])]
        at[node].append(len(labels));labels.append((node,start,parent))
    for node,code in enumerate(codes):
        if mode=='rx' or all(d.hi_ps<=quarter_min for d in points[code]):insert(node,code,None)
        for label in list(at[node]):
            _,start,_=labels[label]
            covered=(all(d.lo_ps>=quarter_max for d in points[code]) if mode=='tx'
                else all(d.lo_ps-hi>=rx_span for d,hi in zip(points[code],upper[start])))
            if covered:
                path=[];cursor=label
                while cursor is not None:
                    index,_,cursor=labels[cursor];path.append(codes[index])
                path.reverse()
                if len(path)>=2:return path
            for nxt in edges[node]:insert(nxt,start,label)
    return None


def select(corners,mode,coarse_count,fine_count):
    p=policy(mode,coarse_count,fine_count);points=vectors(corners,coarse_count,fine_count);path=None;gap_used=None
    for gap in (p['target_gap_ps'],p['maximum_gap_ps']):
        path=find_path(points,gap,mode,p['quarter_min_ps'],p['quarter_max_ps'],p['rx_span_ps'])
        if path is not None:gap_used=gap;break
    base=dict(policy=p,all_fifteen_input_curves_present=True,raw_codes_per_curve=len(points),
        native_characterization_verified=False,updates_qualified=False,legal_code_table_admitted=False,
        electrical_qualification_passed=False,qualified_phy=False)
    if path is None:return dict(base,common_sequence_found=False,codes=[],reason='No common monotone interval path satisfies the required range and 20 ps maximum gap')
    selected={}
    for corner in PVT:
        for edge in ('rise','fall'):
            lookup={d.code:d for d in corners[corner][edge]}
            selected[f'{corner}/{edge}']=[lookup[code] for code in path]
    # Existing independent contract validator rejects an invented code order,
    # overlapping intervals or a largest-possible increment above policy.
    if list(common_legal_codes(selected,p['maximum_gap_ps']))!=path:raise ValueError('Selected interval path cannot reproduce the common-code contract')
    witnesses=[]
    for name,table in selected.items():
        minimum=min(b.lo_ps-a.hi_ps for a,b in zip(table,table[1:]));maximum=max(b.hi_ps-a.lo_ps for a,b in zip(table,table[1:]))
        span=table[-1].lo_ps-table[0].hi_ps
        coverage=(table[0].hi_ps<=p['quarter_min_ps'] and table[-1].lo_ps>=p['quarter_max_ps'] if mode=='tx' else span>=p['rx_span_ps'])
        if minimum<=0 or maximum>20 or not coverage:raise ValueError('Common range or legal gap witness failed')
        witnesses.append(dict(curve=name,first_upper_ps=table[0].hi_ps,last_lower_ps=table[-1].lo_ps,
            conservative_span_ps=span,minimum_increment_ps=minimum,maximum_increment_ps=maximum,required_range_covered=True))
    return dict(base,common_sequence_found=True,codes=path,raw_coarse_fine=[dict(code=c,coarse=c//fine_count,fine=c%fine_count) for c in path],
        search_gap_ps=gap_used,target_10ps_gaps_met=all(w['maximum_increment_ps']<=10 for w in witnesses),
        witnesses=witnesses,selected_curves={name:[asdict(d) for d in table] for name,table in selected.items()},
        scope='Proposed common interval sequence only; complete native provenance, dense PVT/clock coverage, updates and physical/PHY admission remain separate')
