#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Advance each original differential-restoration candidate independently through gated component/link/RC diagnostics."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
VARIANTS=['track_t8_r7','track_t16_r7']
STAGES=dict(components=('qualify_receiver_differential_restore.py','receiver_components','components_passed'),
    coupled=('probe_corrected_driver_differential_restore.py','corrected_native_link','coupled_link_passed'),
    rc=('validate_receiver_differential_restore_rc.py','receiver_differential_restore_rc','receiver_rc_passed'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def relative(value,namespace):
    p=Path(value)
    if p.is_absolute() or '..' in p.parts or not p.is_relative_to('build/diagnostics/'+namespace):
        raise ValueError('Unexpected downstream artifact namespace')
    return p


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,InvocationID'],check=True,capture_output=True,text=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def prepare(stage,source,unit,parent=None,comparison=None):
    if stage not in STAGES:raise ValueError('Select a declared downstream stage')
    relative(str(source.relative_to(ROOT)),'receiver_differential_downstream' if stage=='rc' else 'receiver_physical_followup')
    m=json.loads((source/'manifest.json').read_text())
    if stage=='rc':
        if m['identity'].get('stage')!='components':raise ValueError('RC must follow the matching component handoff')
    else:
        relative(m['matrix'],'receiver_differential_restore_matrix')
    live=owner(unit)
    if live['ActiveState']!='active' or live['MainPID']=='0':raise ValueError('Require the exact live prerequisite owner')
    paths=[source/'manifest.json']+[ROOT/'scripts'/n for n in [NAME,'env.sh',STAGES[stage][0],
        'qualify_receiver_differential_restore.py','probe_receiver_differential_restore.py','layout_receiver_differential_restore.py']]
    details={}
    if stage=='coupled':
        if parent is None or comparison is None:raise ValueError('Coupled diagnostics require the preserved driver fixture and comparison')
        details=dict(parent=str(relative(str(parent.relative_to(ROOT)),'analog_link_pilot')),
            comparison=str(relative(str(comparison.relative_to(ROOT)),'driver_native_restore')))
        paths += [parent/'manifest.json',comparison/'manifest.json']
    identity=dict(stage=stage,source=str(source.relative_to(ROOT)),unit=unit,owner=live,variants=VARIANTS,
        max_parallel_variants=2,no_outer_lease=True,details=details,
        files={str(p.relative_to(ROOT)):sha(p) for p in paths},
        scope='Resource handoff only. Separate variant workers; native transport before components/coupled diagnostics, all sixty components before RC. Scientific producers enforce original fixtures and model/code/evidence gates. No selected-PHY or release promotion.')
    out=ROOT/'build/diagnostics/receiver_differential_downstream'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    return out


def wait_result(source,variant,unit,expected,unchanged,state):
    receipt=source/(variant+'_result.json')
    while True:
        unchanged()
        if receipt.is_file():
            row=json.loads(receipt.read_text())
            if row.get('variant')!=variant:raise ValueError('Prerequisite result variant changed')
            return row,dict(path=str(receipt.relative_to(ROOT)),sha256=sha(receipt))
        summary=source/'summary.json'
        if summary.is_file():
            rows=json.loads(summary.read_text())['results'];matches=[r for r in rows if r.get('variant')==variant]
            if len(matches)>1:raise ValueError('Duplicate prerequisite variant result')
            return (matches[0] if matches else dict(variant=variant)),dict(path=str(summary.relative_to(ROOT)),sha256=sha(summary))
        live=owner(unit)
        if live!=expected:
            if receipt.is_file() or summary.is_file():continue
            raise ValueError('Exact prerequisite owner changed before terminal evidence')
        atomic(state,dict(status='waiting_for_prerequisite',variant=variant,owner=live,qualified_phy=False))
        time.sleep(20)


def admitted_native(row,variant):
    if row.get('variant')!=variant:raise ValueError('Native receipt variant changed')
    if row.get('native_clock_passed') is not True:return None
    replay=relative(row['root'],'receiver_replay');layout=relative(row['layout'],'receiver_layout')
    if sha(ROOT/replay/'manifest.json')!=row['manifest_sha256'] or sha(ROOT/replay/'summary.json')!=row['report_sha256']:
        raise ValueError('Native prerequisite report changed')
    m=json.loads((ROOT/replay/'manifest.json').read_text());r=json.loads((ROOT/replay/'summary.json').read_text())
    if (m['identity'].get('differential_restore_variant')!=variant or m['identity']['layout']!=str(layout) or
        r.get('manifest_sha256')!=row['manifest_sha256'] or r.get('diagnostic_complete') is not True or r.get('native_clock_passed') is not True):
        raise ValueError('Native prerequisite differs from selected variant/geometry')
    return replay,layout


def admitted_components(row,variant):
    if row.get('variant')!=variant:raise ValueError('Component receipt variant changed')
    if row.get('components_passed') is not True:return None
    campaign=relative(row['components'],'receiver_components')
    if sha(ROOT/campaign/'summary.json')!=row['report_sha256'] or sha(ROOT/campaign/'manifest.json')!=row['manifest_sha256']:
        raise ValueError('Component prerequisite report changed')
    r=json.loads((ROOT/campaign/'summary.json').read_text())
    if r.get('manifest_sha256')!=row['manifest_sha256'] or r.get('required')!=60 or r.get('passed_cases')!=60 or r.get('passed') is not True:
        raise ValueError('Require all sixty passing component cases')
    # The scientific RC producer rechecks complete task coverage and its exact
    # current native family before any simulation can be dispatched.
    return campaign


def dispatch(variants,execute):
    if not variants or len(variants)!=len(set(variants)) or any(v not in VARIANTS for v in variants):
        raise ValueError('Select declared variants once each')
    with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(execute,variants))


def run(out):
    relative(str(out.relative_to(ROOT)),'receiver_differential_downstream')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    if i['stage'] not in STAGES or i['variants']!=VARIANTS or i.get('max_parallel_variants')!=2 or i.get('no_outer_lease') is not True:
        raise ValueError('Unexpected downstream dispatch policy')
    def unchanged():
        if sha(out/'manifest.json')!=stamp or any(sha(ROOT/n)!=h for n,h in i['files'].items()):raise ValueError('Downstream handoff context changed')
    def command(args,label):
        unchanged()
        with (out/(label+'.log')).open('w') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3','scripts/'+STAGES[i['stage']][0]]+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        p.check_returncode();unchanged();return (out/(label+'.log')).read_text().strip().splitlines()[-1]
    def evaluate(variant):
        row,proof=wait_result(ROOT/i['source'],variant,i['unit'],i['owner'],unchanged,out/(variant+'_state.json'))
        stage=i['stage'];field=STAGES[stage][2]
        if stage=='rc':
            campaign=admitted_components(row,variant)
            if campaign is None:return dict(variant=variant,status='held_components_not_admitted',qualified_phy=False)
            args=['prepare',str(campaign)]
        else:
            native=admitted_native(row,variant)
            if native is None:return dict(variant=variant,status='held_native_not_admitted',qualified_phy=False)
            replay,layout=native
            args=['prepare',str(layout),'--replay',str(replay)] if stage=='components' else ['prepare',i['details']['parent'],str(replay),i['details']['comparison']]
        atomic(out/(variant+'_state.json'),dict(status='preparing_'+stage,qualified_phy=False))
        inside=Path(command(args,variant+'_prepare'))
        if not inside.is_relative_to('/work/OpenLVDS'):raise ValueError('Unexpected container result path')
        artifact=relative(str(inside.relative_to('/work/OpenLVDS')),STAGES[stage][1])
        capture_manifest(out/(variant+'_prepared.json'),dict(variant=variant,artifact=str(artifact),prerequisite=proof,
            manifest_sha256=sha(ROOT/artifact/'manifest.json'),qualified_phy=False))
        atomic(out/(variant+'_state.json'),dict(status='running_'+stage,artifact=str(artifact),qualified_phy=False))
        command(['run',str(artifact)]+(['--jobs','2'] if stage=='components' else []),variant+'_run')
        report=ROOT/artifact/'summary.json';r=json.loads(report.read_text())
        if stage=='components':passed=r.get('required')==60 and r.get('passed_cases')==60 and r.get('passed') is True
        else:
            if r.get('diagnostic_complete') is not True or r.get('manifest_sha256')!=sha(ROOT/artifact/'manifest.json'):
                raise ValueError('Incomplete or changed downstream diagnostic')
            passed=r.get('receiver_rc_passed' if stage=='rc' else 'passed') is True
        key='components' if stage=='components' else 'artifact'
        return dict(variant=variant,**{key:str(artifact),field:bool(passed)},manifest_sha256=sha(ROOT/artifact/'manifest.json'),
            report_sha256=sha(report),prerequisite=proof,qualified_phy=False)
    def execute(variant):
        try:result=evaluate(variant)
        except Exception as error:result=dict(variant=variant,status='held_for_diagnosis',error=str(error),qualified_phy=False)
        capture_manifest(out/(variant+'_result.json'),result)
        atomic(out/(variant+'_state.json'),dict(status='completed' if result.get(STAGES[i['stage']][2]) is True else 'held_for_diagnosis',qualified_phy=False))
        return result
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior downstream handoff retained')
        atomic(out/'state.json',dict(status='running_variant_handoffs',qualified_phy=False))
        results=dispatch(i['variants'],execute);unchanged()
        capture_manifest(out/'summary.json',dict(results=results,manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_resource_handoff',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare');a.add_argument('stage',choices=STAGES);a.add_argument('source',type=Path)
    a.add_argument('--producer-unit',required=True);a.add_argument('--parent',type=Path);a.add_argument('--driver-comparison',type=Path)
    a=sub.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.stage,a.source.resolve(),a.producer_unit,a.parent.resolve() if a.parent else None,a.driver_comparison.resolve() if a.driver_comparison else None),flush=True)
    else:run(a.artifact.resolve())
