#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read the explicit 300 MHz run ledger without changing dispatcher tickets."""
import argparse
import json
from pathlib import Path
from xyce_profile_300 import ROOT,sha
from check_release_300 import check


def read(path):
    return json.loads(path.read_text()) if path.is_file() else None


def status(root=ROOT,verify=False):
    ledger=read(root/'qualification_runs_300.json')
    rows=[]
    for entry in ledger['runs']:
        directory=(root/entry['artifact']).resolve()
        if not directory.is_relative_to(root.resolve()):
            raise ValueError('Experiment outside OpenLVDS')
        state=read(directory/'state.json')
        interrupted=read(directory/'interruption.json')
        summary=read(directory/'summary.json')
        progress=read(directory/'progress.json')
        errors=[];cases=[]
        for path in sorted(directory.glob('*/summary.json')):
            row=read(path)
            error=row.get('error')
            if error:
                errors.append(dict(case=path.parent.name,error=error))
            result=row.get('result') or {}
            if result:
                source=result.get('source',result)
                cases.append(dict(case=path.parent.name,complete=row.get('complete'),
                                  source_screen_passed=result.get('source_screen_passed'),
                                  half_cycle_error_ps=source.get('mean_half_cycle_error_ps'),
                                  native_terminal_stress_passed=result.get('native_terminal_stress_passed')))
            if verify:
                if row.get('complete') is not True:
                    continue  # Never inspect a live/partial trace as qualified data.
                for name,h in row.get('files',{}).items():
                    if Path(name).name!=name or sha(path.parent/name)!=h:
                        errors.append(dict(case=path.parent.name,error='Retained output changed: '+name))
                task=row['task'].get('parent_task',row['task'])
                if task.get('stop'):
                    from native_binary_raw_v2 import validate
                    try:
                        validate(path.parent/'bench.raw',set(),task['stop'])
                    except (ValueError,OSError) as exc:
                        errors.append(dict(case=path.parent.name,error=str(exc)))
        recorded=(interrupted or state or {}).get('status','prepared' if (directory/'manifest.json').exists() else 'missing')
        complete=recorded=='complete' and summary is not None
        count=len(summary.get('rows',[])) if summary else (progress or {}).get('completed',0)
        outcome='interrupted' if interrupted else 'missing'
        if complete:
            outcome='fail' if errors or count!=entry['expected_cases'] else 'pass'
        elif recorded in ['failed','held_physical_failed','held_rc_failed']:
            outcome='fail'
        elif recorded in ['running','hardening','extracting']:
            outcome='in_progress'
        if entry['role']=='obsolete':
            outcome='obsolete'
        rows.append(dict(id=entry['id'],artifact=entry['artifact'],role=entry['role'],recorded_state=recorded,
                         completed_cases=count,expected_cases=entry['expected_cases'],
                         execution_outcome=outcome,errors=errors,circuit_cases=cases,
                         release_admitted=False))
    release=check(root)
    return dict(schema='openlvds-state-300-v1',runs=rows,
                missing_or_failed_release_gates=[r['gate'] for r in release['gates'] if r['state']!='pass'],
                qualified_phy=release['qualified_phy'],
                note='Execution pass means complete simulation output, not circuit or release acceptance. Running is recorded producer state, not a liveness check.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify-complete',action='store_true')
    a=p.parse_args()
    print(json.dumps(status(verify=a.verify_complete),indent=2))
