#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched 100 ps linear-source diagnostic; preserve both fresh references."""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import bank_entry_waveform_300_v2 as waveform
import matched_entry_materials_300_v1 as materials
import probe_tg2_entry_domain_300_v1 as baseline
import two_bank_entry_measure_300_v2 as metrology
import probe_tg2_next_bank_early_300_v2 as previous
import replay_tg2_loaded_native_300_v2 as replay
from spice_dispatch import lease

ROOT=previous.ROOT
SOURCE=previous.SOURCE
PARENT=ROOT/'build/diagnostics/tg2_next_bank_early_zero_pilot_300_v2/23dee609d6ca5e51'
SOURCE_BANK=previous.PARENT
VERSION='matched-linear-100ps-entry-native-diagnostic-300-v1'
CONTEXT='matched_entry_pilot_300_v1'
SETTINGS=((100,.5),(100,.6))
sha=previous.sha
atomic=previous.atomic


def require_reference(proof):
    base=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v1/5a13c2fa7eabefdd'
    m,inputs=baseline.require_reference(base)
    pm=json.loads((proof/'manifest.json').read_text());pi=pm['identity'];pr=json.loads((proof/'summary.json').read_text())
    parent=ROOT/'build/diagnostics/tg2_entry_domain_pilot_300_v1/b98f2003774d19d6'
    task=json.loads((parent/'manifest.json').read_text())['tasks'][0]
    if (proof.parent!=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v2' or pi['version']!=replay.VERSION
            or proof.name!=hashlib.sha256(json.dumps(pi,sort_keys=True).encode()).hexdigest()[:16]
            or pi['parent']!=str(parent.relative_to(ROOT)) or pi['cases']!=['0']
            or json.loads((proof/'state.json').read_text())!=dict(status='complete',cases=1,qualified_phy=False)
            or pr['all_selected_loaded_native_metrics_reproduced'] is not True or len(pr['rows'])!=1
            or pr['rows'][0]['task']!=task or pr['qualified_phy'] is not False or pr['whole_bank_admitted'] is not False
            or not all(pr['rows'][0][k] is True for k in ('all_original_metrics_reproduced',
                'independent_two_bank_metrics_reproduced','source_point_passed'))):
        raise ValueError('Require exact independently verified 250ps/60% boundary point')
    for n,h in pi['inputs'].items():
        if sha(ROOT/n)!=h or (n in inputs and inputs[n]!=h):raise ValueError('Boundary proof input changed')
        inputs[n]=h
    for n in ('manifest.json','summary.json','state.json'):
        inputs[str((proof/n).relative_to(ROOT))]=sha(proof/n)
    return m,inputs


def specifications(base):
    required=dict(process='ss',temperature=40,frequency_mhz=310,coarse=0,fine=0,cycles=8,stop_ns=40,load_ff=20)
    if any(base[k]!=v for k,v in required.items()):raise ValueError('Require the original fastest-clock loaded zero specification')
    return [dict(base,input_slew_ps=slew,duty=duty) for slew,duty in SETTINGS]


def fixture(out,source_identity,library,spec,centered):
    text,obs=materials.fixture(out,source_identity,library,spec,centered)
    return 'OpenLVDS '+VERSION+'\n'+text.split('\n',1)[1],obs


def prepare(proof):
    baseline,evidence=require_reference(proof)
    sm=SOURCE.bound(SOURCE_BANK,full=False);si=sm['identity'];library=(PARENT/'bank.spice').read_text()
    if library!=(SOURCE_BANK/SOURCE.VARIANT/'bank.spice').read_text():raise ValueError('Actual baseline library changed')
    specs=specifications(baseline['identity']['spec'])
    paths=[PARENT/'bank.spice',SOURCE_BANK/'manifest.json',ROOT/'clocking_300mhz.json']
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**evidence,**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),source_bank=str(SOURCE_BANK.relative_to(ROOT)),
        reference_proof=str(proof.relative_to(ROOT)),inputs=inputs,
        guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},specifications=specs,
        waveform=waveform.VERSION,ideal_input_roundoff_ps=waveform.ROUNDING_PS,
        bench_current_card=SOURCE.numerical_trial.CARD,bench_current_dc_a=0,bench_current_peak_a=.001,
        power_excludes_external_bench_load=True,
        max_workers=1,priority=2,profile_sha256=sha(ROOT/'clocking_300mhz.json'),
        source_full_bank_coverage_qualified=False,source_active_numerical_parity_qualified=False,
        scope='Matched 100ps linear-source diagnostic at SS40/310MHz only; no boundary coverage, calibration or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_text(library);tasks=[]
    for k in range(4):
        spec=specs[k%2];centered=k<2;folder=out/str(k);folder.mkdir()
        text,obs=fixture(out,si,library,spec,centered)
        (folder/'bench.cir').write_text(text);atomic(folder/'observations.json',obs)
        tasks.append(dict(id=str(k),setting=k%2,spec=spec,centered=centered,next_coarse=0,next_fine=0,
                          files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False))
    bound(out)
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or i['source_bank']!=str(SOURCE_BANK.relative_to(ROOT))
            or (i['max_workers'],i['priority'])!=(1,2) or i['profile_sha256']!=sha(ROOT/'clocking_300mhz.json')
            or i['waveform']!=waveform.VERSION or i['ideal_input_roundoff_ps']!=waveform.ROUNDING_PS
            or i['bench_current_card']!=SOURCE.numerical_trial.CARD or i['bench_current_dc_a']!=0
            or i['bench_current_peak_a']!=.001 or i['power_excludes_external_bench_load'] is not True
            or i['source_full_bank_coverage_qualified'] is not False or i['source_active_numerical_parity_qualified'] is not False
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}
            or m['qualified_phy'] is not False):raise ValueError('Entry-domain experiment identity changed')
    if any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items()):
        raise ValueError('Captured entry-domain input changed')
    proof=ROOT/i['reference_proof']
    if (proof.parent!=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v2'
            or any(str((proof/n).relative_to(ROOT)) not in i['guards'] for n in ('manifest.json','summary.json','state.json'))):
        raise ValueError('Entry-domain loaded reference binding changed')
    baseline=previous.bound(PARENT,full=False);sm=SOURCE.bound(SOURCE_BANK,full=False)
    if i['specifications']!=specifications(baseline['identity']['spec']):raise ValueError('Entry-domain specifications changed')
    library=(PARENT/'bank.spice').read_text()
    if (out/'bank.spice').read_text()!=library or sha(out/'bank.spice')!=m['bank_sha256']:
        raise ValueError('Native entry-domain library changed')
    expected=[]
    for k in range(4):
        spec=i['specifications'][k%2];folder=out/str(k);text,obs=fixture(out,sm['identity'],library,spec,k<2)
        if (folder/'bench.cir').read_text()!=text or json.loads((folder/'observations.json').read_text())!=obs:
            raise ValueError('Native entry stimulus or complete observation maps changed')
        expected.append(dict(id=str(k),setting=k%2,spec=spec,centered=k<2,next_coarse=0,next_fine=0,
                             files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    if m['tasks']!=expected:raise ValueError('Entry-domain coverage or fresh references changed')
    return m


def pilot_passed(rows,pairs):
    if len(rows)!=4 or [r['task']['id'] for r in rows]!=[str(k) for k in range(4)] or set(pairs)!={str(k) for k in range(2)}:
        raise ValueError('Require all four cases and both fresh numerical pairs')
    for k in range(2):
        a,b=rows[k]['task'],rows[k+2]['task']
        if (a['centered'] is not True or b['centered'] is not False or a['spec']!=b['spec']
                or (a['spec']['input_slew_ps'],a['spec']['duty'])!=SETTINGS[k]
                or a['setting']!=k or b['setting']!=k):raise ValueError('Mismatched entry-domain numerical pair')
    return bool(all(r['error'] is None and r['result']['two_bank_zero_pilot_passed'] for r in rows)
                and all(v['passed'] is True for v in pairs.values()))


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial entry-domain experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=metrology.measure(folder,json.loads((folder/'observations.json').read_text()),task['spec'],next_coarse=0,next_fine=0)
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        pairs={str(k):previous.numerical_pair(out,rows,k+2,k) for k in range(2)}
        passed=pilot_passed(rows,pairs);bound(out)
        atomic(out/'summary.json',dict(rows=rows,active_numerical_controls=pairs,matched_entry_pilot_passed=passed,
            source_full_bank_coverage_qualified=False,source_active_numerical_parity_qualified=False,
            shared_wire_rc_qualified=False,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',type=Path)
    a=p.parse_args();target=a.artifact.resolve();print(prepare(target) if a.action=='prepare' else run(target),flush=True)
