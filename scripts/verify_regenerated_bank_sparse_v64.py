#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure every complete regenerated joint-RC sparse waveform."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import probe_regenerated_bank_sparse_v63 as pilot
import run_native_binary_v2 as runner
from native_binary_raw_v2 import read

ROOT=pilot.ROOT
sha=pilot.sha
VERSION='independent-complete-regenerated-joint-rc-sparse-native-waveforms-v64.1'
CONTEXT='regenerated_bank_sparse_verification_v64'


def verify(parent):
    m=pilot.bound(parent);i=m['identity']
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=5,errors=0,qualified_phy=False):
        raise ValueError('Require all five numerically complete sparse waveforms')
    aggregate=json.loads((parent/'summary.json').read_text());rows=[]
    paths=[parent/n for n in ('manifest.json','state.json','summary.json','bank.spice')]
    paths += [ROOT/n for n in i['inputs']]+[Path(__file__),Path(runner.__file__)]
    for task in m['tasks']:
        folder=parent/task['id'];row=json.loads((folder/'summary.json').read_text())
        required={'bench.cir','bench.ngspice.cir','bench.raw','console.log','ngspice.log'}
        if (row['task']!=task or row['spec']!=task['spec'] or row['error'] is not None
                or aggregate['rows'][int(task['id'])]!=row or not required<=set(row['files'])
                or any(sha(folder/n)!=h for n,h in row['files'].items())
                or (folder/'bench.ngspice.cir').read_text()!=runner.translate((folder/'bench.cir').read_text())[0]):
            raise ValueError('Complete sparse native task evidence changed')
        log=(folder/'ngspice.log').read_text();counts=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log)
        _,wave=read(folder/'bench.raw')
        if (len(counts)!=1 or int(counts[0])!=len(wave) or 'Total analysis time (seconds)' not in log
                or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)',log)):
            raise ValueError('Native sparse log does not attest completed transient')
        measured=pilot.measure(folder,i,task['spec'])
        if measured!=row['result']:raise ValueError('Full sparse native waveform does not remeasure exactly')
        rows.append(dict(spec=task['spec'],result=measured,error=None))
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    # Test voltage and physical control observation failures on a complete
    # nonzero code, preserving every original trace and circuit statement.
    task=m['tasks'][0];folder=parent/task['id'];bad=deepcopy(i)
    bad['observations']['controls'][0]['node']='IN'
    if pilot.measure(folder,bad,task['spec'])['control_settling_passed']:
        raise ValueError('Clock-data substitution was accepted as a static sparse control')
    bad=deepcopy(i)
    for device in bad['observations']['devices']:device['limit_v']=.1
    if pilot.measure(folder,bad,task['spec'])['terminal_screen_passed']:
        raise ValueError('Wrong sparse native voltage limit was accepted')
    comparison=pilot.metrics.compare([dict(spec=pilot.zero.spec(),result=i['zero_result'],error=None),*rows])
    if comparison!=aggregate['comparison']:raise ValueError('Sparse comparison cannot regenerate')
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),case_ids=[t['id'] for t in m['tasks']],
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})
    pilot.bound(parent)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Sparse inputs changed during verification')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():bound(out);return out
    out.mkdir(parents=True);pilot.zero.baseline.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    result=dict(rows=rows,comparison=comparison,full_native_waveforms_remeasured=True,all_declared_cases_consumed=True,
        reused_zero_evidence=i['evidence'],negative_controls=[dict(fault='clock_as_static_control',rejected=True),dict(fault='wrong_voltage_limit',rejected=True)],
        complete_sparse_bank_screen_passed=comparison['sparse_native_screen_passed'],whole_bank_rc_retained=True,
        dense_legal_code_coverage_proven=False,legal_code_table_admitted=False,electrical_qualification_passed=False,
        qualified_phy=False,scope=pilot.SCOPE,files={'manifest.json':sha(out/'manifest.json')})
    pilot.zero.baseline.atomic(out/'summary.json',result);bound(out);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];r=json.loads((out/'summary.json').read_text())
    parent=ROOT/i['parent'];original=json.loads((parent/'summary.json').read_text())
    expected=[dict(spec=row['spec'],result=row['result'],error=None) for row in original['rows']]
    source=json.loads((parent/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['case_ids']!=['0','1','2','3','4'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(out/n)!=h for n,h in r['files'].items()) or not r['full_native_waveforms_remeasured']
            or not r['all_declared_cases_consumed'] or not r['whole_bank_rc_retained']
            or len(r['negative_controls'])!=2 or not all(c['rejected'] for c in r['negative_controls'])
            or r['rows']!=expected or r['comparison']!=original['comparison']
            or r['comparison']!=pilot.metrics.compare([dict(spec=pilot.zero.spec(),result=source['zero_result'],error=None),*expected])
            or r['complete_sparse_bank_screen_passed']!=r['comparison']['sparse_native_screen_passed']
            or any(r[k] for k in ('qualified_phy','electrical_qualification_passed','legal_code_table_admitted','dense_legal_code_coverage_proven'))):
        raise ValueError('Independent complete sparse receipt changed')
    pilot.bound(parent);return i


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path)
    print(verify(p.parse_args().parent.resolve()),flush=True)
