#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expand corrected DLL qualification after measured screening, then require all-PVT stability."""
import argparse
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
VARIANT='ota_w8_c16'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,InvocationID'],check=True,capture_output=True,text=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def relative(value,namespace):
    p=Path(value)
    if p.is_absolute() or '..' in p.parts or not p.is_relative_to('build/diagnostics/'+namespace):raise ValueError('Unexpected DLL continuation namespace')
    return p


def prepare(qualification,prerequisite,unit):
    relative(str(qualification.relative_to(ROOT)),'dll_qualification')
    relative(str(prerequisite.relative_to(ROOT)),'dll_architecture')
    m=json.loads((qualification/'manifest.json').read_text())
    if m['identity'].get('variant')!=VARIANT or len(m['tasks'])!=336 or len({t['id'] for t in m['tasks']})!=336:
        raise ValueError('Require the exact corrected 336-case DLL qualification')
    live=owner(unit)
    if live['ActiveState']!='active' or live['MainPID']=='0':raise ValueError('Require the exact live stability-screen owner')
    paths=[qualification/n for n in ['manifest.json','storage_source_admission.json','full.spice','fast.spice','requirements.json']]
    paths += [prerequisite/'manifest.json',prerequisite/'run.py']
    paths += [ROOT/'scripts'/n for n in [NAME,'env.sh','qualify_dll_storage.py','qualify_dll_candidate.py','measure_dll_storage_stability.py','stability_evidence.py']]
    identity=dict(qualification=str(qualification.relative_to(ROOT)),prerequisite=str(prerequisite.relative_to(ROOT)),unit=unit,owner=live,
        files={str(p.relative_to(ROOT)):sha(p) for p in paths},full_inputs=m['identity']['full_models']['inputs'],
        max_native_workers=3,no_outer_lease=True,
        scope='Resource handoff only. Complete passing three-corner measured margins/step validation before all 336 native cases; complete passing native qualification before all fifteen measured stability corners. Original scientific producers, numerical policies and six actual SPICE slots retained. Recovery, readiness, OTA, RC and full PHY remain separate gates.')
    out=ROOT/'build/diagnostics/dll_storage_full_followup'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def screen_receipt(qualification,row):
    if row.get('stability_screen_passed') is not True:raise ValueError('Measured stability screen did not pass')
    if row.get('qualification')!=str(qualification.relative_to(ROOT)):raise ValueError('Stability handoff selected another DLL qualification')
    report=ROOT/relative(row['report'],'dll_qualification')
    if not report.is_relative_to(qualification/'stability_screen') or report.name!='summary.json' or sha(report)!=row['report_sha256']:
        raise ValueError('Measured stability-screen report changed or belongs to another scope')
    return report


def full_native(qualification):
    m=json.loads((qualification/'manifest.json').read_text());r=json.loads((qualification/'summary.json').read_text())
    expected={t['id'] for t in m['tasks']}
    if (len(m['tasks'])!=336 or len(expected)!=336 or r.get('passed') is not True or
        r.get('manifest_sha256')!=sha(qualification/'manifest.json') or set(r.get('tasks',{}))!=expected or
        any(t.get('status')!='passed' for t in r['tasks'].values()) or
        len(r.get('dll_full_fast_comparisons',[]))!=len(m['comparisons']) or
        any(c.get('passed') is not True for c in r['dll_full_fast_comparisons'])):
        raise ValueError('Require all 336 native cases and every captured full/fast comparison')
    return r


def all_pvt(qualification,report):
    if not report.is_relative_to(qualification/'stability_all_pvt') or report.name!='summary.json':raise ValueError('Require all-PVT stability from this exact qualification')
    m=json.loads((qualification/'manifest.json').read_text());req=json.loads((qualification/'requirements.json').read_text())
    r=json.loads(report.read_text());s=json.loads((report.parent/'manifest.json').read_text())
    expected={f'{p}_{t}' for p in req['process_corners'] for t in req['temperatures_c']};actual=[c['corner'] for c in r['results']]
    if (len(expected)!=15 or len(actual)!=15 or set(actual)!=expected or r.get('all_pvt') is not True or r.get('passed') is not True or
        r.get('full_inputs')!=m['identity']['full_models']['inputs'] or r.get('manifest_sha256')!=sha(report.parent/'manifest.json') or
        s['qualification_manifest_sha256']!=sha(qualification/'manifest.json') or s['library_sha256']!=sha(qualification/'full.spice')):
        raise ValueError('Incomplete or stale all-PVT stability evidence')
    for corner in r['results']:
        models=corner.get('models',[]);steps=corner.get('transient_validation',[])
        if corner.get('passed') is not True or len(models)!=3 or any(
            model.get('passed') is not True or model.get('model_valid') is not True or
            not (model['phase_margin_min_deg']>=60 and model['gain_margin_min_db']>=6) for model in models):
            raise ValueError('All-PVT measured loop-margin gate failed')
        if len(steps)!=2 or {step['target_mhz'] for step in steps}!={390,410} or any(
            step.get('passed') is not True or not 0<=step['amplitude_relative_error']<=.25 or
            not 0<=step['settling_relative_error']<=.25 for step in steps):
            raise ValueError('All-PVT measured step-validation gate failed')
    # The original measurement command has already run stability_evidence.verified
    # on every waveform and model. Retain that report and its source identity.
    return r


def run(out):
    relative(str(out.relative_to(ROOT)),'dll_storage_full_followup');m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if sha(out/'manifest.json')!=stamp or i.get('max_native_workers')!=3 or i.get('no_outer_lease') is not True or any(sha(ROOT/n)!=h for n,h in i['files'].items()):raise ValueError('Full DLL handoff context changed')
    def command(script,args,label):
        unchanged()
        with (out/(label+'.log')).open('w') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3','scripts/'+script]+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        p.check_returncode();unchanged();return (out/(label+'.log')).read_text().strip().splitlines()[-1]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior full-DLL resource context retained')
        try:
            prerequisite=ROOT/i['prerequisite'];receipt=prerequisite/'summary.json'
            while not receipt.is_file():
                unchanged();live=owner(i['unit'])
                if live!=i['owner']:
                    if receipt.is_file():break
                    raise ValueError('Exact measured-stability owner terminated before completed evidence')
                if (prerequisite/'error.json').is_file():raise ValueError('Measured stability screen held for diagnosis')
                atomic(out/'state.json',dict(status='waiting_measured_stability_screen',owner=live,qualified_phy=False));time.sleep(20)
            qualification=ROOT/i['qualification'];stability=screen_receipt(qualification,json.loads(receipt.read_text()))
            capture_manifest(out/'screen_admission.json',dict(report=str(stability.relative_to(ROOT)),report_sha256=sha(stability),receipt_sha256=sha(receipt),qualified_phy=False))
            atomic(out/'state.json',dict(status='running_full_336_native_cases',qualified_phy=False))
            command('qualify_dll_storage.py',['run',i['qualification'],'--stage','full','--stability',str(stability.relative_to(ROOT)),'--jobs','3'],'full_native')
            full_native(qualification)
            capture_manifest(out/'native_full_result.json',dict(native_full_passed=True,report_sha256=sha(qualification/'summary.json'),qualification_manifest_sha256=sha(qualification/'manifest.json'),qualified_phy=False))
            atomic(out/'state.json',dict(status='running_all_fifteen_stability_corners',qualified_phy=False))
            inside=Path(command('measure_dll_storage_stability.py',[i['qualification'],'--all-pvt'],'all_pvt_stability'))
            if not inside.is_relative_to('/work/OpenLVDS/build/diagnostics/dll_qualification'):raise ValueError('Unexpected all-PVT stability output')
            report=ROOT/inside.relative_to('/work/OpenLVDS');all_pvt(qualification,report)
            unchanged();capture_manifest(out/'summary.json',dict(native_full_passed=True,all_pvt_stability_passed=True,qualification=i['qualification'],
                native_report_sha256=sha(qualification/'summary.json'),all_pvt_stability=str(report.relative_to(ROOT)),all_pvt_stability_sha256=sha(report),
                full_inputs=i['full_inputs'],manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
            atomic(out/'state.json',dict(status='native_and_all_pvt_stability_passed',qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(error),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare');a.add_argument('qualification',type=Path);a.add_argument('prerequisite',type=Path);a.add_argument('--producer-unit',required=True)
    a=sub.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.qualification.resolve(),a.prerequisite.resolve(),a.producer_unit),flush=True)
    else:run(a.artifact.resolve())
