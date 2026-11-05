#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure all routed periodic clock transport and slew cases."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import probe_regenerated_bank_periodic_v67 as pilot
import run_native_binary_v2 as runner
from native_binary_raw_v2 import read

ROOT=pilot.ROOT
sha=pilot.sha
VERSION='independent-complete-regenerated-joint-rc-periodic-clock-and-slew-v68.1'
CONTEXT='regenerated_bank_periodic_verification_v68'


def verify(parent):
    m=pilot.bound(parent);i=m['identity']
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=4,errors=0,qualified_phy=False):
        raise ValueError('Require all four numerically complete periodic waveforms')
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
            raise ValueError('Complete periodic native task evidence changed')
        log=(folder/'ngspice.log').read_text();counts=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log)
        _,wave=read(folder/'bench.raw')
        if (len(counts)!=1 or int(counts[0])!=len(wave) or 'Total analysis time (seconds)' not in log
                or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)',log)):
            raise ValueError('Native periodic log does not attest completed transient')
        measured=pilot.measure(folder,i,task['spec'])
        if measured!=row['result']:raise ValueError('Full periodic native waveform does not remeasure exactly')
        rows.append(dict(spec=task['spec'],result=measured,error=None))
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    # Test voltage and physical control observation failures on a complete
    # nonzero code, preserving every original trace and circuit statement.
    task=m['tasks'][0];folder=parent/task['id'];bad=deepcopy(i)
    bad['observations']['controls'][0]['node']='IN'
    if pilot.measure(folder,bad,task['spec'])['control_settling_passed']:
        raise ValueError('Clock-data substitution was accepted as a static periodic control')
    bad=deepcopy(i)
    for device in bad['observations']['devices']:device['limit_v']=.1
    if pilot.measure(folder,bad,task['spec'])['terminal_screen_passed']:
        raise ValueError('Wrong periodic native voltage limit was accepted')
    wrong=dict(task['spec'],duty=.6 if task['spec']['duty']==.4 else .4)
    if pilot.measure(folder,i,wrong)['input_timing_stimulus_passed']:
        raise ValueError('Wrong periodic input duty was accepted')
    comparison=dict(all_periodic_transport_cases_passed=all(r['result']['periodic_transport_screen_passed'] for r in rows),all_current_clock_interface_cases_passed=all(r['result']['current_clock_interface_screen_passed'] for r in rows))
    if comparison!=aggregate['comparison']:raise ValueError('Periodic comparison cannot regenerate')
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),case_ids=[t['id'] for t in m['tasks']],
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})
    pilot.bound(parent)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Periodic inputs changed during verification')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():bound(out);return out
    out.mkdir(parents=True);pilot.zero.baseline.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    result=dict(rows=rows,comparison=comparison,full_native_waveforms_remeasured=True,all_declared_cases_consumed=True,
        required_zero_evidence=i['evidence'],negative_controls=[dict(fault='clock_as_static_control',rejected=True),dict(fault='wrong_voltage_limit',rejected=True),dict(fault='wrong_input_duty',rejected=True)],
        all_periodic_transport_cases_passed=comparison['all_periodic_transport_cases_passed'],
        all_current_clock_interface_cases_passed=comparison['all_current_clock_interface_cases_passed'],whole_bank_rc_retained=True,
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
            or i['case_ids']!=['0','1','2','3'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(out/n)!=h for n,h in r['files'].items()) or not r['full_native_waveforms_remeasured']
            or not r['all_declared_cases_consumed'] or not r['whole_bank_rc_retained']
            or len(r['negative_controls'])!=3 or not all(c['rejected'] for c in r['negative_controls'])
            or r['rows']!=expected or r['comparison']!=original['comparison']
            or r['all_periodic_transport_cases_passed']!=r['comparison']['all_periodic_transport_cases_passed']
            or r['all_current_clock_interface_cases_passed']!=r['comparison']['all_current_clock_interface_cases_passed']
            or any(r[k] for k in ('qualified_phy','electrical_qualification_passed','legal_code_table_admitted','dense_legal_code_coverage_proven'))):
        raise ValueError('Independent complete periodic receipt changed')
    pilot.bound(parent);return i


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path)
    print(verify(p.parse_args().parent.resolve()),flush=True)
