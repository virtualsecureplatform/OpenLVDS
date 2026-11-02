#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Wait for complete fast-frontend DC evidence before independent source clocks."""
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
VARIANTS=['fast_tia_r2','fast_tia_r4']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,InvocationID'],check=True,capture_output=True,text=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def prepare(matrix,parent,unit):
    if not matrix.is_relative_to(ROOT/'build/diagnostics/receiver_tia_fast_matrix') or not parent.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use the fast-frontend DC matrix and exact N8 reference')
    m=json.loads((matrix/'manifest.json').read_text());prior=json.loads((parent/'manifest.json').read_text())
    if (len(m['identity']['children'])!=15 or set(m['identity']['candidate_sha256'])!={'control',*VARIANTS} or
            prior['identity'].get('first_restorer_variant')!='restore_lvt_n8'):
        raise ValueError('Require all fifteen declared source corners and original N8 reference')
    live=owner(unit)
    if live['ActiveState']!='active' or live['MainPID']=='0':raise ValueError('Require the exact live DC producer')
    paths=[matrix/'manifest.json']+[parent/n for n in ['manifest.json','summary.json','source_clock_admission.json']]
    paths += [ROOT/'scripts'/n for n in [NAME,'receiver_tia_fast_frontend_clock.py','matrix_receiver_tia_fast_frontend.py',
        'screen_receiver_tia_fast_frontend.py','receiver_tia_fast_frontend.py','receiver_tia_restore.py','env.sh']]
    identity=dict(matrix=str(matrix.relative_to(ROOT)),parent=str(parent.relative_to(ROOT)),unit=unit,owner=live,
        files={str(p.relative_to(ROOT)):sha(p) for p in paths},max_parallel_variants=2,no_outer_lease=True,
        scope='Resource-only handoff. Each candidate requires all fifteen original DC/current/stress cases before original three full 80 ns source-clock controls. Only an attested identical unchanged N8 reference can be adopted. Actual simulators share the existing six slots; no native/component/PHY promotion.')
    out=ROOT/'build/diagnostics/receiver_tia_fast_clock_followup'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def admitted(matrix,report):
    m=json.loads((matrix/'manifest.json').read_text())
    if report.get('diagnostic_complete') is not True or report.get('required_pvt')!=15 or report.get('manifest_sha256')!=sha(matrix/'manifest.json'):
        raise ValueError('Require the completed exact fifteen-corner DC report')
    expected=dict(required=15,completed=15,passed_cases=15,source_dc_passed=True)
    if report['variants'].get('control')!=expected:raise ValueError('Exact N8 DC control must pass')
    if set(report['variants'])!={'control',*VARIANTS} or set(m['identity']['candidate_sha256'])!={'control',*VARIANTS}:
        raise ValueError('Unexpected fast-frontend candidate coverage')
    return [v for v in VARIANTS if report['variants'][v]==expected]


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_tia_fast_clock_followup'):raise ValueError('Use a prepared fast-frontend clock handoff')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or i.get('max_parallel_variants')!=2 or i.get('no_outer_lease') is not True or
                any(sha(ROOT/n)!=h for n,h in i['files'].items())):raise ValueError('Fast-frontend clock handoff changed')
    def evaluate(variant):
        try:
            unchanged();command=[str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3','scripts/receiver_tia_fast_frontend_clock.py']
            p=subprocess.run(command+['prepare',i['parent'],'--dc-matrix',i['matrix'],'--variant',variant],cwd=ROOT,capture_output=True,text=True)
            (out/(variant+'_prepare.log')).write_text(p.stdout+p.stderr);p.check_returncode()
            inside=Path(p.stdout.strip().splitlines()[-1])
            if not inside.is_relative_to('/work/OpenLVDS/build/diagnostics/receiver_clamp'):raise ValueError('Unexpected source-clock output')
            relative=inside.relative_to('/work/OpenLVDS');root=ROOT/relative
            with (out/(variant+'_run.log')).open('w') as log:
                subprocess.run(command+['run',str(relative)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            receipt=root/'source_clock_admission.json';gate=json.loads(receipt.read_text())
            if (gate.get('source_clock_passed') is not True or gate.get('manifest_sha256')!=sha(root/'manifest.json') or
                    gate.get('report_sha256')!=sha(root/'summary.json')):raise ValueError('No exact passing source-clock admission')
            unchanged();r=dict(variant=variant,root=str(relative),admission=gate,admission_sha256=sha(receipt),qualified_phy=False)
        except Exception as error:r=dict(variant=variant,status='held_for_diagnosis',error=str(error),qualified_phy=False)
        capture_manifest(out/(variant+'_result.json'),r);return r
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior fast-frontend clock handoff retained')
        try:
            matrix=ROOT/i['matrix'];receipt=matrix/'summary.json'
            while not receipt.is_file():
                unchanged();live=owner(i['unit'])
                if live!=i['owner']:
                    if receipt.is_file():break
                    raise ValueError('Exact DC owner terminated before complete evidence')
                state=matrix/'state.json'
                if state.exists() and json.loads(state.read_text()).get('status')=='held_for_diagnosis':raise ValueError('DC pilots held for diagnosis')
                atomic(out/'state.json',dict(status='waiting_full_dc',owner=live,qualified_phy=False));time.sleep(20)
            variants=admitted(matrix,json.loads(receipt.read_text()))
            results=[dict(variant=v,status='held_dc_not_admitted',qualified_phy=False) for v in VARIANTS if v not in variants]
            capture_manifest(out/'dc_admission.json',dict(report_sha256=sha(receipt),variants=variants,qualified_phy=False))
            atomic(out/'state.json',dict(status='running_source_clocks',variants=variants,qualified_phy=False))
            with ThreadPoolExecutor(max_workers=2) as pool:results += list(pool.map(evaluate,variants))
            unchanged();passed=bool(variants and all(r.get('admission',{}).get('source_clock_passed') is True for r in results if r['variant'] in variants))
            capture_manifest(out/'summary.json',dict(results=results,qualified_phy=False,manifest_sha256=stamp,scope=i['scope']))
            atomic(out/'state.json',dict(status='completed_admitted_source_clocks' if passed else 'held_for_diagnosis',qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(error),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('matrix',type=Path);a.add_argument('parent',type=Path);a.add_argument('--producer-unit',required=True)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.matrix.resolve(),a.parent.resolve(),a.producer_unit),flush=True)
    else:run(a.artifact.resolve())
