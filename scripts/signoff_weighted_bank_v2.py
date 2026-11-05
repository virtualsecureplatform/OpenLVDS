#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Continue the powered repaired bank from detailed routes through physical checks.

Keep the accepted routing artifact immutable. Physical evidence does not admit
native delay, legal codes, full-PVT timing or the complete PHY.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import harden_weighted_bank_v18 as parent_flow

ROOT=parent_flow.ROOT
sha=parent_flow.sha
atomic=parent_flow.atomic
VERSION='repaired-weighted-bank-post-route-physical-checks-v2.1'
CONTEXT='weighted_bank_signoff_v2'
START='Odb.RemoveRoutingObstructions'
STOP='Checker.LVS'
ZERO_METRICS=('route__drc_errors','magic__drc_error__count',
              'klayout__drc_error__count','design__lvs_error__count',
              'antenna__violating__nets','antenna__violating__pins',
              'design__critical_disconnected_pin__count','design__xor_difference__count')


def referenced_files(value):
    """All state view leaves must be existing absolute files; metrics are separate."""
    if value is None:return []
    if isinstance(value,dict):
        return [p for item in value.values() for p in referenced_files(item)]
    if not isinstance(value,str) or not Path(value).is_absolute() or not Path(value).is_file():
        raise ValueError('Missing or invalid initial-state view: '+str(value))
    return [Path(value)]


def prepare(parent):
    m=parent_flow.bound(parent);i=m['identity']
    r=json.loads((parent/'summary.json').read_text())
    if (r.get('routing_bringup_passed') is not True or r.get('route_drc_errors')!=0
        or r.get('placement_check',{}).get('passed') is not True):
        raise ValueError('Require the accepted repaired-bank route and physical supply checks')
    run=ROOT/r['run'];states=list(run.glob('*detailedrouting/state_out.json'))
    if len(states)!=1:raise ValueError('Require exactly one detailed-routing state')
    state=states[0];payload=json.loads(state.read_text())
    if payload['metrics'].get('route__drc_errors')!=0:raise ValueError('Initial route DRC failed')
    files=[parent/n for n in ['manifest.json','config.json','summary.json','state.json',
                              'check_db.log','power_checks.tsv','connections.tsv','placements.tsv','ports.tsv']]
    files += [state,Path(__file__),Path(parent_flow.__file__)]
    files += referenced_files({k:v for k,v in payload.items() if k!='metrics'})
    config=json.loads((parent/'config.json').read_text())
    if config!=i['configuration']:raise ValueError('Parent configuration mismatch')
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),
        initial_state=str(state.relative_to(ROOT)),configuration=config,start=START,stop=STOP,
        inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in files},
        tools=parent_flow.old.tool_identity())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    atomic(out/'config.json',config)
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or i['start']!=START or i['stop']!=STOP
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(Path(n) if Path(n).is_absolute() else ROOT/n)!=h for n,h in i['inputs'].items())
        or parent_flow.old.tool_identity()!=i['tools']
        or json.loads((out/'config.json').read_text())!=i['configuration']):
        raise ValueError('Post-route physical context changed')
    parent_flow.bound(ROOT/i['parent'])
    return m


def physical_pass(returncode,target_complete,check,metrics):
    return (returncode==0 and target_complete and check is not None and check.get('passed') is True
            and all(k in metrics and metrics[k]==0 for k in ZERO_METRICS))


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior physical experiment')
        atomic(out/'state.json',dict(status='checking_physical',qualified_phy=False))
        tag='weighted-signoff-'+out.name[:12]
        argv=[sys.executable,'-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],
              '-p','sky130A','-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar',
              '--from',START,'--to',STOP,'--with-initial-state',str(ROOT/i['initial_state']),
              '--run-tag',tag,str(out/'config.json')]
        try:
            with (out/'flow.log').open('w') as log:
                p=subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT)
            bound(out);folder=out/'runs'/tag
            states=sorted(folder.glob('*/state_out.json'),key=lambda x:x.stat().st_mtime)
            latest=json.loads(states[-1].read_text()) if states else {}
            metrics,nonfinite=parent_flow.old.sanitize(latest.get('metrics',{}))
            db=Path(latest['odb']) if latest.get('odb') else None
            check=parent_flow.check_db(out,db,
                json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity']['spec'],
                i['configuration']['MACROS']) if db and db.is_file() else None
            target=bool(list(folder.glob('*checker-lvs/state_out.json')))
            passed=physical_pass(p.returncode,target,check,metrics)
            outputs={str(q.relative_to(ROOT)):sha(q) for q in states}
            if latest:
                outputs.update({str(q.relative_to(ROOT)) if q.is_relative_to(ROOT) else str(q):sha(q)
                    for q in referenced_files({k:v for k,v in latest.items() if k!='metrics'})})
            result=dict(returncode=p.returncode,target_step=STOP,target_step_completed=target,
                run=str(folder.relative_to(ROOT)),last_state=str(states[-1].relative_to(ROOT)) if states else None,
                metrics=metrics,nonfinite_metric_paths=nonfinite,placement_check=check,
                outputs=outputs,physical_implementation_passed=passed,
                electrical_qualification_passed=False,qualified_phy=False,
                scope='Whole repaired-bank post-route connectivity/fill/GDS DRC/LVS/antenna checks only; fresh passive bank RC, native timing, legal codes, all-PVT and complete PHY remain required')
            atomic(out/'summary.json',result)
            atomic(out/'state.json',dict(status='physical_checks_complete' if passed else 'held_physical_failed',qualified_phy=False))
            return result
        except Exception as exc:
            atomic(out/'state.json',dict(status='physical_exception',error=str(exc),qualified_phy=False))
            raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
