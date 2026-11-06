#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retain every native raw-code result; select only universally passing codes.

Complete measured failures are excluded, never converted into invented delay
intervals. Missing, changed or failed-to-measure traces remain incomplete.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
import probe_regular_regenerated_full_range_v301 as source

ROOT=source.ROOT
sha=source.sha
selector=source.selector
VERSION='complete-native-raw-results-universal-code-eligibility-v303.1'
CONTEXT='native_eligible_sequence_v303'


def propose(points):
    policy=selector.policy('tx',16,32);path=None;gap=None
    for candidate in (10.,20.):
        path=selector.find_path(points,candidate,'tx',policy['quarter_min_ps'],policy['quarter_max_ps'])
        if path is not None:gap=candidate;break
    base=dict(policy=policy,all_fifteen_input_curves_present=True,raw_codes_per_curve=512,
        eligible_raw_codes_per_curve=len(points),native_characterization_verified=False,
        updates_qualified=False,legal_code_table_admitted=False,electrical_qualification_passed=False,qualified_phy=False)
    if path is None:return dict(base,common_sequence_found=False,codes=[],reason='No common eligible interval path covers the required TX range within the 20 ps gap')
    names=[f'{corner}/{edge}' for corner in selector.PVT for edge in ('rise','fall')]
    curves={name:[points[code][index] for code in path] for index,name in enumerate(names)}
    if list(selector.common_legal_codes(curves,20))!=path:raise ValueError('Eligible sequence fails independent common-order validation')
    witnesses=[]
    for name,table in curves.items():
        lo=min(b.lo_ps-a.hi_ps for a,b in zip(table,table[1:]));hi=max(b.hi_ps-a.lo_ps for a,b in zip(table,table[1:]))
        covered=table[0].hi_ps<=policy['quarter_min_ps'] and table[-1].lo_ps>=policy['quarter_max_ps']
        if lo<=0 or hi>20 or not covered:raise ValueError('Eligible sequence range/gap witness failed')
        witnesses.append(dict(curve=name,first_upper_ps=table[0].hi_ps,last_lower_ps=table[-1].lo_ps,
            conservative_span_ps=table[-1].lo_ps-table[0].hi_ps,minimum_increment_ps=lo,maximum_increment_ps=hi,required_range_covered=True))
    return dict(base,common_sequence_found=True,codes=path,raw_coarse_fine=[dict(code=c,coarse=c//32,fine=c%32) for c in path],
        search_gap_ps=gap,target_10ps_gaps_met=all(w['maximum_increment_ps']<=10 for w in witnesses),witnesses=witnesses,
        selected_curves={name:[asdict(d) for d in table] for name,table in curves.items()},
        scope='Common ordering of universally passing reference-clock codes only; clock variation, updates, physical ROM and PHY remain unqualified')


def assess(rows):
    matrix=source.specifications()
    if len(rows)!=7680 or any(r.get('error') is not None or r.get('result') is None for r in rows):
        raise ValueError('Every raw code/PVT must have a complete measured result, including failures')
    actual=[source.key(r['spec']) for r in rows]
    if len(set(actual))!=7680 or set(actual)!={source.key(s) for s in matrix}:
        raise ValueError('Require all 7680 unique exact raw-code/PVT conditions')
    records=[];passing={code:{} for code in range(512)};failed={code:[] for code in range(512)}
    for row in rows:
        s=row['spec'];r=row['result'];code=s['coarse']*32+s['fine'];corner=s['process']+':'+str(s['temperature'])
        if (r.get('whole_bank_rc_retained') is not True or r.get('input_timing_stimulus_passed') is not True
            or any(type(r.get(flag)) is not bool for flag in source.sparse.NATIVE_FLAGS)
            or any(len(r.get(field,[]))!=count or any(type(d.get('passed')) is not bool for d in r[field])
                for field,count in (('terminal_stress',1529),('programming_gates',173),('controls',86)))
            or set(r.get('edge_delays_ps',{}))!={'rise','fall'}
            or any(not math.isfinite(v) for values in r['edge_delays_ps'].values() for v in values)):
            raise ValueError('Incomplete native observations, invalid reference stimulus or nonfinite measured delays')
        passed=source.sparse.point_passed(r)
        reasons=[flag for flag in source.sparse.NATIVE_FLAGS if not r[flag]]
        counts={field:sum(not d['passed'] for d in r[field]) for field in ('terminal_stress','programming_gates','controls')}
        record=dict(pvt=corner,code=code,coarse=s['coarse'],fine=s['fine'],native_point_passed=passed,
            failed_original_gates=reasons,failed_native_observation_counts=counts,
            measured_edge_counts={edge:len(v) for edge,v in r['edge_delays_ps'].items()})
        if passed:
            record['edges']={edge:dict(lo_ps=min(values),hi_ps=max(values)) for edge,values in r['edge_delays_ps'].items()}
            passing[code][corner]=record['edges']
        else:failed[code].append(corner)
        records.append(record)
    eligible=[code for code in range(512) if not failed[code]]
    points={code:tuple(source.Delay(code,**passing[code][corner][edge]) for corner in selector.PVT for edge in ('rise','fall')) for code in eligible}
    proposal=propose(points)
    return dict(complete_7680_measured_raw_results=True,raw_code_count=512,eligible_codes=eligible,
        excluded_codes=[dict(code=code,failed_pvt=failed[code]) for code in range(512) if failed[code]],
        all_raw_codes_passed=len(eligible)==512,raw_point_records=sorted(records,key=lambda r:(r['pvt'],r['code'])),
        proposed_common_sequence=proposal,common_sequence_found=proposal['common_sequence_found'],
        all_clock_conditions_characterized=False,bank_configuration_selected=False,legal_code_table_admitted=False,
        updates_qualified=False,rx_range_qualified=False,physical_rom_qualified=False,whole_clock_qualified=False,
        electrical_qualification_passed=False,qualified_phy=False)


def verify(parent):
    m=source.bound(parent);i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=7680,consumed_cases=106,errors=0,qualified_phy=False)
        or len(r.get('rows',[]))!=7574 or r.get('inherited_rows')!=[s['row'] for s in i['inherited_sources']]):
        raise ValueError('Complete original full-range characterization required; never skip missing traces')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json','bank.spice')]
    for k,(spec,row) in enumerate(zip(i['specs'],r['rows'])):
        case=parent/str(k);deck=case/'bench.cir'
        if (row.get('task')!=dict(id=str(k),spec=spec,deck_sha256=sha(deck)) or row.get('spec')!=spec
            or row.get('error') is not None or row!=json.loads((case/'summary.json').read_text())
            or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(row['files'])
            or any(sha(case/n)!=h for n,h in row['files'].items()) or deck.read_text()!=source.fixture(parent,i,spec)
            or source.measure(case,i,spec)!=row['result']):
            raise ValueError('Original full-range native result does not reproduce, including failed points')
        paths += [case/'summary.json',*[case/n for n in row['files']]]
    rows=r['inherited_rows']+r['rows']
    if r['comparison']!=source.assess(rows):raise ValueError('Original conservative full-range report changed')
    result=assess(rows)
    paths += [ROOT/n for n in i['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None)
        and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},
        numpy_version=source.source.np.__version__,byteorder=sys.byteorder)
    source.bound(parent)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Native eligibility inputs changed during verification')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(result,all_original_native_results_reproduced=True),indent=2)+'\n')
    (out/'proposal.json').write_text(json.dumps(result['proposed_common_sequence'],indent=2)+'\n')
    (out/'state.json').write_text(json.dumps(dict(status='complete',raw_cases=7680,eligible_codes=len(result['eligible_codes']),
        common_sequence_found=result['common_sequence_found'],qualified_phy=False),indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('full_range',type=Path);a=p.parse_args();print(verify(a.full_range.resolve()),flush=True)
