#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Publish measured electrical tables, preserving absent and failed corners."""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import sys
from spice_library import library
from evidence_scope import matches as evidence_matches

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',choices=['schematic','full-rc','fast-rc'],default='full-rc')
    a=p.parse_args();req=json.loads((ROOT/'requirements.json').read_text())
    base={'schematic':'analog','full-rc':'analog_extracted','fast-rc':'analog_fast'}[a.model]
    source=hashlib.sha256((ROOT/'analog/openlvds.spice').read_bytes()).hexdigest()
    try:expected=library(extracted=a.model!='schematic',fast=a.model=='fast-rc')[0]
    except (ValueError,KeyError,FileNotFoundError):expected=None
    rows=[];inputs={}
    metrics={'driver':['differential_min_v','differential_max_v','common_mode_min_v',
        'common_mode_max_v','propagation_min_ps','propagation_max_ps'],
        'dll':['quarter_phase_min_ps','quarter_phase_max_ps','feedback_error_max_ps','phase_bad_max_v'],
        'receiver':[],
        'receiver_rate':['clock_mhz','output_load_ff','high_valid_min_ps','low_valid_min_ps','rising_edges','falling_edges']}
    for test,process,temp in itertools.product(metrics,req['process_corners'],req['temperatures_c']):
        path=ROOT/f'build/{base}/{test}_{process}_{temp}/summary.json'
        evidence=json.loads(path.read_text()) if path.exists() else {}
        scope_test='receiver' if test=='receiver_rate' else test
        ok=evidence.get('passed',False) and evidence_matches(evidence,path.with_name('source.spice'),expected,scope_test)
        row=dict(test=test,process=process,temperature_c=temp,passed=ok,
                 detail=evidence.get('error',('' if ok else 'Failed or stale circuit evidence') if evidence else 'Missing characterization'))
        row.update({m:evidence.get(m) for m in metrics[test]})
        if test=='receiver':
            points=evidence.get('points',[])
            row['decisions_passed']=sum(bool(x['passed']) for x in points)
            row['decisions_total']=len(points)
        rows.append(row)
        if path.exists():inputs[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    out=ROOT/'build/characterization'/a.model;out.mkdir(parents=True,exist_ok=True)
    columns=list(dict.fromkeys(k for row in rows for k in row))
    with (out/'electrical.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,columns);writer.writeheader();writer.writerows(rows)
    summary=dict(passed=all(r['passed'] for r in rows),model=a.model,source_sha256=source,
        inputs=inputs,rows=rows,scope='Fixed-supply measured electrical table; not a digital Liberty timing model')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(passed=summary['passed'],rows=len(rows),output=str(out.relative_to(ROOT))),indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
