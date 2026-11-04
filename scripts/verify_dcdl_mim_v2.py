#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent custom-MIM DCDL source verification; no physical admission."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import probe_digital_dcdl_cap_v2 as pilot
import probe_digital_dcdl_batch_v2 as dense
import verify_digital_clocking_v2 as previous

h=pilot.h
ROOT=h.ROOT
MODULES={'digital_dcdl_cap_v2':pilot,'digital_dcdl_batch_v2':dense}
REQUIRED=previous.REQUIRED


def report(out):
    out=out.resolve()
    if out.parent.name not in MODULES or not out.is_relative_to(ROOT/'build/diagnostics'):
        raise ValueError('Require a custom-MIM DCDL context')
    module=MODULES[out.parent.name]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=module.bound(out);state=json.loads((out/'state.json').read_text())
        if state['status']!='source_screen_complete' or state['cases']!=len(m['tasks']):raise ValueError('Source campaign not terminal')
        rows=json.loads((out/'summary.json').read_text())['rows']
        if [r['task'] for r in rows]!=m['tasks']:raise ValueError('Incomplete or duplicated source rows')
        files={str((out/n).relative_to(ROOT)):h.sha(out/n) for n in ['manifest.json','summary.json','state.json']}
        samples=[];numerical=stress_failures=0
        for row in rows:
            task=row['task'];folder=out/task['id']
            if json.loads((folder/'summary.json').read_text())!=row or any(h.sha(folder/n)!=v for n,v in row['files'].items()):
                raise ValueError('Source output changed')
            if row['error'] is not None:
                if row['result'] is not None:raise ValueError('Failed case has timing result')
                numerical+=1
            else:
                if not REQUIRED<=set(row['files']):raise ValueError('Missing terminal source files')
                previous.export_matches_raw(folder)
                result=module.measure(folder,task) if module is dense else module.measure(folder)
                if result!=row['result']:raise ValueError('Independent custom-MIM remeasurement differs')
                stress_failures+=not result['custom_mos_stress_passed']
                values=result['samples'] if module is dense else [dict(code=task['spec']['fine'],
                    rise_delay_ps=result['rise_delay_ps'],fall_delay_ps=result['fall_delay_ps'])]
                for value in values:
                    samples.append(dict(process=task['spec']['process'],temperature=task['spec']['temperature'],
                        coarse=task['spec']['coarse'],variant=task['spec'].get('variant','mim2x2_strong_return'),**value))
            files.update({str((folder/n).relative_to(ROOT)):v for n,v in row['files'].items()})
            files[str((folder/'summary.json').relative_to(ROOT))]=h.sha(folder/'summary.json')
        groups=[]
        for key in sorted({(s['variant'],s['process'],s['temperature'],s['coarse']) for s in samples}):
            values=sorted([s for s in samples if (s['variant'],s['process'],s['temperature'],s['coarse'])==key],key=lambda s:s['code'])
            codes=[s['code'] for s in values]
            if len(set(codes))!=len(codes):raise ValueError('Duplicate code samples')
            complete=codes==list(range(32))
            metric={}
            for edge in ['rise','fall']:
                delays=[s[edge+'_delay_ps'] for s in values]
                metric[edge+'_range_ps']=[min(delays),max(delays)]
                metric[edge+'_monotonic']=all(a<b for a,b in zip(delays,delays[1:]))
                metric[edge+'_max_adjacent_step_ps']=max((b-a for a,b in zip(delays,delays[1:])),default=None) if complete else None
            groups.append(dict(variant=key[0],process=key[1],temperature=key[2],coarse=key[3],dense_32_codes=complete,**metric))
        overlaps=[]
        for key in sorted({(s['variant'],s['process'],s['temperature']) for s in samples}):
            a=[s for s in samples if (s['variant'],s['process'],s['temperature'])==key and s['coarse']==0]
            b=[s for s in samples if (s['variant'],s['process'],s['temperature'])==key and s['coarse']==1]
            if a and b:
                overlaps.append(dict(variant=key[0],process=key[1],temperature=key[2],
                    rise_overlap_ps=max(s['rise_delay_ps'] for s in a)-min(s['rise_delay_ps'] for s in b),
                    fall_overlap_ps=max(s['fall_delay_ps'] for s in a)-min(s['fall_delay_ps'] for s in b)))
        module.bound(out)
        return dict(artifact=str(out.relative_to(ROOT)),cases=len(rows),samples=samples,groups=groups,overlaps=overlaps,
            numerical_errors=numerical,custom_stress_failures=stress_failures,
            legal_code_table_admitted=False,qualified_phy=False,source_only=True,
            scope='Observed source delay range/steps, coarse overlap and all custom MOS stresses; '
                  'uncertainty bounds, common all-PVT sequence, actual 390--410 MHz pulse transport and physical qualification remain required',
            consumer_sha256=h.sha(Path(__file__)),witness_files=files)


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=h.sha(out/'manifest.json'),
        summary_sha256=h.sha(out/'summary.json'),consumer_sha256=h.sha(Path(__file__)))
    receipt=ROOT/'build/diagnostics/dcdl_mim_v2_verification'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True);body=json.dumps(result,indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior MIM receipt changed')
    if not (receipt/'summary.json').exists():h.write(receipt/'summary.json',body)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
