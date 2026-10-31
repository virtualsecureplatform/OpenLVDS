#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the agreed extracted-link matrix; never treat diagnostics as release evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def matrix():
    req=json.loads((ROOT/'requirements.json').read_text())
    cases=[]
    def add(name,**config):cases.append(dict(name=name,config=dict(dll_phase=True,settled_start=True,**config)))
    add('nominal',bits=req['minimum_extracted_nominal_bits'])
    for process,temp in itertools.product(req['process_corners'],req['temperatures_c']):
        if (process,temp)==('tt',25):continue
        add(f'pvt_{process}_{temp}',bits=req['minimum_extracted_corner_bits'],process=process,temperature=temp)
    for mhz,duty,skew in itertools.product(req['clock_test_mhz'],req['clock_duty'],req['channel_skew_ps']):
        if (mhz,duty,skew)==(400,.5,0):continue
        add(f'timing_{mhz}_{duty}_{skew}',bits=512,mhz=mhz,duty=duty,skew_ps=skew)
    for shift in [-req['minimum_sampling_margin_ps'],req['minimum_sampling_margin_ps']]:
        add(f'aperture_{shift}',bits=512,eye_shift_ps=shift)
    for clock in ['openpll-rtl','openpll-physical']:
        add(clock,bits=512,clock_source=clock)
    return cases

def main():
    p=argparse.ArgumentParser();p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--fast-rc',action='store_true');p.add_argument('--list',action='store_true')
    p.add_argument('--bundle',type=Path,help='Run against an isolated staged PHY')
    p.add_argument('--case',help='Run a single named case')
    a=p.parse_args();cases=matrix()
    if a.case:cases=[c for c in cases if c['name']==a.case]
    if not cases:p.error('Unknown case')
    if a.list:print(json.dumps(cases,indent=2));return 0
    if a.bundle:
        from phy_candidate import load
        load(a.bundle,a.fast_rc)
    out=a.bundle.resolve()/'regression' if a.bundle else ROOT/'build/regression';out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').unlink(missing_ok=True)
    def run(case):
        cmd=[sys.executable,str(ROOT/'scripts/simulate_link.py')]
        for k,v in case['config'].items():
            flag='--'+k.replace('_','-')
            if isinstance(v,bool):
                if v:cmd.append(flag)
            else:cmd.extend([flag,str(v)])
        if a.fast_rc:cmd.append('--fast-rc')
        if a.bundle:cmd.extend(['--bundle',str(a.bundle)])
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (out/(case['name']+'.log')).write_text(r.stdout+r.stderr)
        try:summary=json.loads(r.stdout)
        except ValueError:summary=dict(passed=False,error='No result; see case log')
        return dict(case=case,passed=r.returncode==0 and summary.get('passed',False),result=summary)
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:results=list(pool.map(run,cases))
    summary=dict(passed=all(r['passed'] for r in results),complete_matrix=not bool(a.case),results=results)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(passed=summary['passed'],cases=len(results),failed=[r['case']['name'] for r in results if not r['passed']]),indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
