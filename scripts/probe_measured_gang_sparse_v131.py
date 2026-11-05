#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete the measured-gang sparse screen with new zero/coarse native runs.

Consume the completed fine31 trace explicitly. No waveform or requirement
substitution: all three points use the identical measured component bank.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import probe_measured_gang_fine_v127 as fine

ROOT=fine.ROOT
zero=fine.zero
sha=fine.sha
VERSION='measured-gang-zero-coarse-with-completed-fine31-native-screen-v131.1'
CONTEXT='measured_gang_sparse_v131'
SCOPE='Three-point measured-component sparse screen: two new zero/coarse runs plus an unchanged completed fine31 trace; TG gang/common bank routing, periodic/PVT/electrical/PHY admission remain unqualified'


def specifications(spec):return [dict(spec,coarse=c,fine=0) for c in (0,1)]


def fixture(out,i,s):
    text=zero.fixture(out,dict(i,spec=s,top=fine.circuit.name(s['profile'])))
    title='OpenLVDS '+zero.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original sparse native fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(parent):
    fi=fine.bound(parent);r=json.loads((parent/'summary.json').read_text());case=parent/'0';row=json.loads((case/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=1,errors=0,qualified_phy=False)
        or r['rows']!=[row] or row['error'] is not None
        or not row['result']['static_native_screen_passed'] or not row['result']['output_slew_domain_passed']
        or any(sha(case/n)!=h for n,h in row['files'].items()) or fine.measure(case,fi)!=row['result']):
        raise ValueError('Require complete unchanged safe measured-gang fine31 trace')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json','bank.spice']]
    paths += [case/'summary.json',*[case/n for n in row['files']],*[ROOT/n for n in fi['inputs']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(fi,version=VERSION,source_fine=str(parent.relative_to(ROOT)),source_fine_result=row['result'],specs=specifications(fi['spec']),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((parent/'bank.spice').read_bytes());tasks=[]
    for k,s in enumerate(i['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,i,s))
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    (out/'manifest.json').write_text(json.dumps(dict(identity=i,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or zero.engine()!='ngspice' or zero.provenance()!=i['simulator'] or i['max_workers']!=2
        or i['specs']!=specifications(i['spec']) or len(m['tasks'])!=2
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
        or sha(out/'bank.spice')!=m['bank_sha256'] or sha(ROOT/i['source_fine']/'bank.spice')!=m['bank_sha256']):
        raise ValueError('Measured-gang sparse context changed')
    row=json.loads((ROOT/i['source_fine']/'0/summary.json').read_text())
    if row['error'] is not None or row['result']!=i['source_fine_result']:raise ValueError('Consumed fine31 result changed')
    for k,t in enumerate(m['tasks']):
        deck=out/str(k)/'bench.cir'
        if t['id']!=str(k) or t['spec']!=i['specs'][k] or sha(deck)!=t['deck_sha256'] or deck.read_text()!=fixture(out,i,t['spec']):
            raise ValueError('Measured-gang sparse fixture changed')
    return m


def compare(rows,fine_result):
    if len(rows)!=2 or any(row['error'] is not None for row in rows):return None
    by={(row['spec']['coarse'],row['spec']['fine']):row['result'] for row in rows}
    if set(by)!={(0,0),(1,0)}:raise ValueError('Sparse screen case coverage changed')
    overlaps={edge+'_ps':fine_result['samples'][1][edge+'_delay_ps']-by[1,0]['samples'][1][edge+'_delay_ps'] for edge in ['rise','fall']}
    headroom=1e6/410/4-max(v for sample in by[0,0]['samples'] for v in sample.values())
    native=all(r['static_native_screen_passed'] and r['output_slew_domain_passed'] for r in [fine_result,*by.values()])
    return dict(coarse_overlap=overlaps,zero_code_fast_quarter_headroom_ps=headroom,
                measured_component_sparse_feasibility_passed=bool(native and headroom>0 and all(v>0 for v in overlaps.values())),
                complete_fine31_trace_consumed=True,whole_bank_rc_retained=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial measured-gang sparse campaign')
        zero.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=wall=None
            try:
                with zero.lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);start=time.monotonic()
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    wall=time.monotonic()-start
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=fine.measure(folder,dict(i,spec=task['spec']));result.update(scope=SCOPE)
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,solver_wall_seconds=wall,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            zero.baseline.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        zero.baseline.atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows,i['source_fine_result']),source_fine=i['source_fine'],scope=SCOPE,qualified_phy=False))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=2,consumed_fine_cases=1,errors=sum(row['error'] is not None for row in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(prepare(a.artifact.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
