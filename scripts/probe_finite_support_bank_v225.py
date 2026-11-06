#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay unchanged native bank with analytically bounded finite-support input.

Retain the known passing 40% and failing 60% endpoint as mandatory parity
references. Zero/coarse are also run, but full four-case waveform parity
requires the original zero/coarse to complete independently. No original
solver is stopped, and no source timing or terminal limit is changed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import finite_support_clock_v224 as waveform
import probe_balanced_isolated_fine_bank_v201 as source
from qualify_repaired_clock_counter_rc_v193 import sha
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
VERSION='unchanged-native-bank-finite-support-input-bounded-parity-v225.1'
CONTEXT='finite_support_bank_replay_v225'
SCOPE='Numerical input-precision experiment on unchanged P20/N10 native component bank; original solver tolerances, all native terminals and all timing gates retained; no full waveform parity/all-PVT/whole-bank/PHY admission'


def specifications():return source.specifications()[:4]


def compare_case(reference,candidate):
    flags=('all_input_output_pulses_present','input_timing_stimulus_passed','full_swing_pulses_passed','unwrapped_native_epoch_passed',
           'pulse_order_and_widths_passed','current_downstream_250ps_slew_domain_passed','period_screen_passed','repeated_delay_screen_passed',
           'zero_code_quarter_passed','terminal_screen_passed','control_settling_passed','current_clock_interface_screen_passed')
    same_flags=all(candidate[k] is reference[k] for k in flags)
    errors={}
    for field in ('edge_delays_ps','output_slews_10_90_ps'):
        diffs=[]
        for edge in ('rise','fall'):
            a=reference[field][edge];b=candidate[field][edge]
            if len(a)!=8 or len(b)!=8 or any(not math.isfinite(v) for v in a+b):raise ValueError('Waveform parity requires all eight finite edge histories')
            diffs += [abs(x-y) for x,y in zip(a,b)]
        errors[field]=max(diffs)
    a={r['device']:r for r in reference['terminal_stress']};b={r['device']:r for r in candidate['terminal_stress']}
    if len(reference['terminal_stress'])!=1473 or len(candidate['terminal_stress'])!=1473 or len(a)!=1473 or a.keys()!=b.keys():raise ValueError('Waveform parity requires all original 1473 MOS')
    differences=[abs(a[n]['maximum_terminal_difference_v']-b[n]['maximum_terminal_difference_v']) for n in a]
    if not all(math.isfinite(v) for v in differences):raise ValueError('Nonfinite native terminal parity')
    stress=max(differences)
    native_safe=all(a[n]['limit_v']==b[n]['limit_v'] and a[n]['passed'] and b[n]['passed'] and b[n]['maximum_terminal_difference_v']<=b[n]['limit_v'] for n in a)
    passed=same_flags and all(v<=1 for v in errors.values()) and stress<=.001 and native_safe and candidate['terminal_screen_passed'] and candidate['control_settling_passed']
    return dict(same_all_original_gate_results=same_flags,maximum_edge_delay_difference_ps=errors['edge_delays_ps'],
        maximum_slew_difference_ps=errors['output_slews_10_90_ps'],maximum_native_terminal_peak_difference_v=stress,
        native_waveform_parity_passed=bool(passed),known_timing_failure_must_be_preserved=True,qualified_phy=False)


def fixture(parent,i,s):
    text=source.fixture(parent,i,s);lines=text.splitlines();old=[n for n,line in enumerate(lines) if line.startswith('BIN IN 0 V={')]
    if len(old)!=1 or lines[0]!='OpenLVDS '+source.VERSION:raise ValueError('Original native input fixture changed')
    expression,proof=waveform.expression(s);lines[0]='OpenLVDS '+VERSION;lines[old[0]]='BIN IN 0 V={'+expression+'}'
    return '\n'.join(lines)+'\n'


def prepare(parent):
    m=source.bound(parent);i=m['identity']
    if engine()!='ngspice' or provenance()!=i['simulator']:raise ValueError('Require unchanged native ngspice environment')
    refs=[];paths=[parent/'manifest.json',parent/source.key(specifications()[0])/'bank.spice']
    for k in (0,1):
        folder=parent/str(k);row=json.loads((folder/'summary.json').read_text())
        if row['task']!=m['tasks'][k] or row['spec']!=specifications()[k] or row['error'] is not None or row['result'] is None or any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Require unchanged complete original fine31 references')
        if source.measure(folder,i,row['spec'])!=row['result']:raise ValueError('Original fine31 references do not reproduce')
        refs.append(row);paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    if refs[0]['result']['current_clock_interface_screen_passed'] is not True or refs[1]['result']['current_clock_interface_screen_passed'] is not False:raise ValueError('Require the original passing 40% and failing 60% pair')
    paths += [ROOT/n for n in i['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(i,version=VERSION,parent=str(parent.relative_to(ROOT)),specs=specifications(),references=refs,
        waveform=waveform.parameters(100,8),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False);tasks=[]
    for k,s in enumerate(identity['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(parent,identity,s));tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['specs']!=specifications() or i['max_workers']!=2 or i['waveform']!=waveform.parameters(100,8)
        or engine()!='ngspice' or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())):raise ValueError('Finite-support native replay context changed')
    if len(m['tasks'])!=4:raise ValueError('Require both parity endpoints, zero and first coarse')
    for k,t in enumerate(m['tasks']):
        f=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(f)) or f.read_text()!=fixture(ROOT/i['parent'],i,t['spec']):raise ValueError('Finite-support fixture changed')
    return m


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial finite-support replay')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=source.measure(folder,i,task['spec'])
                result.update(scope=SCOPE,input_precision_experiment_only=True,full_four_case_waveform_parity_passed=False,qualified_phy=False)
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        parity=[dict(case=str(k),**compare_case(i['references'][k]['result'],rows[k]['result'])) for k in (0,1)] if all(rows[k]['error'] is None for k in (0,1)) else None
        bound(out);atomic(out/'summary.json',dict(rows=rows,original_endpoint_parity=parity,
            full_four_case_waveform_parity_passed=False,all_four_original_reference_cases_required=True,
            all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
