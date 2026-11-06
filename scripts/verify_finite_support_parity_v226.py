#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent four-case native input-precision replay receipt, without reruns."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import exact_rc_candidate as exact
import probe_finite_support_bank_v225 as replay

ROOT=replay.ROOT
VERSION='complete-four-native-case-input-precision-parity-v226.1'
CONTEXT='finite_support_bank_parity_v226'
sha=replay.sha


def assess(rows):
    if len(rows)!=4 or [r['case'] for r in rows]!=['0','1','2','3']:raise ValueError('All four unique original/candidate case pairs are required')
    return dict(full_four_case_waveform_parity_passed=all(r['comparison']['native_waveform_parity_passed'] is True and r['comparison']['same_all_original_gate_results'] is True for r in rows),
        original_passing_and_failing_endpoint_gates_preserved=all(r['comparison']['same_all_original_gate_results'] is True for r in rows),
        all_four_original_reference_cases_present=True,bank_clock_interface_qualified=False,all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False,
        scope='Complete same-DUT four-case input-precision parity only; preservation of the original 60% failure does not qualify that bank or any other DUT/PVT')


def verify(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if i['version']!=replay.VERSION or parent.parent!=ROOT/'build/diagnostics'/replay.CONTEXT:raise ValueError('Require explicit finite-support native replay')
    source=ROOT/i['parent'];original=json.loads((source/'manifest.json').read_text());pairs=[];paths=[]
    # Check complete case availability before the expensive unchanged-parent
    # digest and full-waveform scans. A running unrelated second pilot family
    # is not consumed, changed or stopped by this four-case receipt.
    for k in range(4):
        a=source/str(k);b=parent/str(k)
        if not all((f/'summary.json').exists() for f in (a,b)):raise ValueError('All four original and candidate native cases must be complete')
        ra=json.loads((a/'summary.json').read_text());rb=json.loads((b/'summary.json').read_text())
        for folder,row,task in ((a,ra,original['tasks'][k]),(b,rb,m['tasks'][k])):
            if row['task']!=task or row['spec']!=replay.specifications()[k] or row['error'] is not None or row['result'] is None:raise ValueError('Native parity task/measurement incomplete')
            if any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Native parity waveform/deck/log changed')
            paths += [folder/'summary.json',*[folder/n for n in row['files']]]
        pairs.append((a,ra,b,rb))
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=4,errors=0,qualified_phy=False):raise ValueError('Finite-support replay must finish all four cases')
    replay.bound(parent);replay.source.bound(source)
    paths += [parent/n for n in ('manifest.json','summary.json','state.json')]+[source/'manifest.json',Path(__file__),*[ROOT/n for n in i['inputs']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,candidate=str(parent.relative_to(ROOT)),source=str(source.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},math_runtime=exact.math_runtime())
    rows=[]
    for k,(a,ra,b,rb) in enumerate(pairs):
        golden=replay.source.measure(a,original['identity'],ra['spec'])
        if golden!=ra['result']:raise ValueError('Original complete native parity metrics do not reproduce')
        candidate=replay.source.measure(b,i,rb['spec']);candidate.update(scope=replay.SCOPE,input_precision_experiment_only=True,full_four_case_waveform_parity_passed=False,qualified_phy=False)
        if candidate!=rb['result']:raise ValueError('Candidate complete native parity metrics do not reproduce')
        rows.append(dict(case=str(k),spec=ra['spec'],comparison=replay.compare_case(golden,candidate)))
    result=dict(assess(rows),rows=rows,identity=identity,input_bound=i['waveform'])
    if i['waveform']['global_input_difference_bound_v']>1e-6:raise ValueError('Input precision bound changed')
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()) or exact.math_runtime()!=identity['math_runtime']:raise ValueError('Native parity inputs changed during verification')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=result['full_four_case_waveform_parity_passed'],qualified_phy=False),indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate',type=Path);a=p.parse_args();print(verify(a.candidate.resolve()))
