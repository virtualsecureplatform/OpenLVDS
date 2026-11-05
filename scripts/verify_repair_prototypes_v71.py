#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure complete split-loading or buffered prototypes."""
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import re
import run_native_binary_v2 as runner
from native_binary_raw_v2 import read

ROOT=Path(__file__).resolve().parents[1]
VERSION='independent-complete-native-repair-prototype-comparisons-v71.1'
CONTEXT='repair_prototype_verification_v71'
KINDS=dict(split='probe_split_fine_component_v69',buffered='probe_buffered_bank_v70')


def producer(kind):
    if kind not in KINDS:raise ValueError('Unknown repair prototype kind')
    return importlib.import_module(KINDS[kind])


def verify(parent,kind):
    p=producer(kind);m=p.bound(parent);i=m['identity'];sha=p.sha
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=6,errors=0,qualified_phy=False):
        raise ValueError('Require all six numerically complete prototype cases')
    aggregate=json.loads((parent/'summary.json').read_text());rows=[]
    paths=[parent/n for n in ('manifest.json','state.json','summary.json',*m['libraries'])]
    paths += [ROOT/n for n in i['inputs']]+[Path(__file__),Path(runner.__file__)]
    for task in m['tasks']:
        folder=parent/task['id'];row=json.loads((folder/'summary.json').read_text())
        required={'bench.cir','bench.ngspice.cir','bench.raw','console.log','ngspice.log'}
        if (row['task']!=task or row['spec']!=task['spec'] or row['error'] is not None
                or aggregate['rows'][int(task['id'])]!=row or not required<=set(row['files'])
                or any(sha(folder/n)!=h for n,h in row['files'].items())
                or (folder/'bench.ngspice.cir').read_text()!=runner.translate((folder/'bench.cir').read_text())[0]):
            raise ValueError('Complete prototype native task evidence changed')
        log=(folder/'ngspice.log').read_text();counts=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log)
        _,wave=read(folder/'bench.raw')
        if (len(counts)!=1 or int(counts[0])!=len(wave) or 'Total analysis time (seconds)' not in log
                or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)',log)):
            raise ValueError('Native prototype log does not attest completed transient')
        measured=p.measure(folder,i,task['spec'])
        if measured!=row['result']:raise ValueError('Full prototype native waveform does not remeasure exactly')
        rows.append(dict(spec=task['spec'],result=measured,error=None))
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    task=m['tasks'][0];folder=parent/task['id'];profile=task['spec']['profile'];bad=deepcopy(i)
    bad['observations'][profile]['controls'][0]['node']='IN'
    if p.measure(folder,bad,task['spec'])['control_settling_passed']:
        raise ValueError('Clock data accepted as a static prototype control')
    bad=deepcopy(i)
    for d in bad['observations'][profile]['devices']:d['limit_v']=.1
    if p.measure(folder,bad,task['spec'])['terminal_screen_passed']:
        raise ValueError('Wrong prototype native voltage limit accepted')
    comparison=p.comparisons(rows)
    if comparison!=aggregate['comparison']:raise ValueError('Prototype comparisons cannot regenerate')
    identity=dict(version=VERSION,kind=kind,parent=str(parent.relative_to(ROOT)),case_ids=[t['id'] for t in m['tasks']],
                  inputs={str(f.relative_to(ROOT)):sha(f) for f in paths})
    p.bound(parent)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Prototype inputs changed during remeasurement')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():bound(out);return out
    out.mkdir(parents=True);p.zero.baseline.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    report=dict(rows=rows,comparison=comparison,full_native_waveforms_remeasured=True,all_declared_cases_consumed=True,
        complete_prototype_comparison_verified=True,
        negative_controls=[dict(fault='clock_as_static_control',rejected=True),dict(fault='wrong_voltage_limit',rejected=True)],
        whole_bank_rc_retained=False,added_or_moved_geometry_qualified=False,electrical_qualification_passed=False,
        qualified_phy=False,scope=p.SCOPE,files={'manifest.json':sha(out/'manifest.json')})
    p.zero.baseline.atomic(out/'summary.json',report);bound(out);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];r=json.loads((out/'summary.json').read_text())
    p=producer(i['kind']);sha=p.sha;parent=ROOT/i['parent'];original=json.loads((parent/'summary.json').read_text())
    expected=[dict(spec=row['spec'],result=row['result'],error=None) for row in original['rows']]
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['case_ids']!=list(map(str,range(6))) or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(out/n)!=h for n,h in r['files'].items()) or not r['full_native_waveforms_remeasured']
            or not r['all_declared_cases_consumed'] or not r['complete_prototype_comparison_verified']
            or len(r['negative_controls'])!=2 or not all(c['rejected'] for c in r['negative_controls'])
            or r['rows']!=expected or r['comparison']!=original['comparison'] or r['comparison']!=p.comparisons(expected)
            or any(r[k] for k in ('whole_bank_rc_retained','added_or_moved_geometry_qualified','electrical_qualification_passed','qualified_phy'))):
        raise ValueError('Independent prototype comparison receipt changed')
    p.bound(parent);return i


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('parent',type=Path)
    parser.add_argument('--kind',required=True,choices=KINDS);args=parser.parse_args()
    print(verify(args.parent.resolve(),args.kind),flush=True)
