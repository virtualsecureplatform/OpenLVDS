#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate the two-buffer experiment and independently compare native traces."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_static_phase_clock_drive_v2 as pilot
from native_binary_raw_v2 import validate

ROOT=pilot.ROOT
VERSION='independent-native-two-buffer-phase-clock-drive-verification-v2.1'
CONTEXT='static_phase_clock_drive_verification_v2'
REQUIRED={'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}


def regenerate(out,m):
    parent,bm,report=pilot.checked_baseline(ROOT/m['identity']['receipt'])
    cells,module,devices,added=pilot.libraries(parent,bm)
    if (str(parent.relative_to(ROOT))!=m['identity']['baseline'] or cells!=(out/'cells.spice').read_text()
        or module!=(out/'pair.spice').read_text() or devices!=m['identity']['devices']
        or added!=m['identity']['added_clock_driver_mos']):raise ValueError('Native two-buffer RC/topology/witness regeneration changed')
    return parent,bm,devices


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);parent,bm,devices=regenerate(out,m)
        state=json.loads((out/'state.json').read_text());aggregate=json.loads((out/'summary.json').read_text())['rows']
        if (state['status']!='clock_drive_pilot_complete' or state['cases']!=4 or len(aggregate)!=4
            or state['errors']!=sum(r['error'] is not None for r in aggregate)):
            raise ValueError('Require the four terminal clock-drive cases')
        paths=[out/n for n in ['manifest.json','state.json','summary.json',*m['libraries']]];rows=[];comparisons=[]
        for task,retained in zip(m['tasks'],aggregate):
            folder=out/task['id'];r=json.loads((folder/'summary.json').read_text());spec=task['spec']
            if (r!=retained or r['task']!=task or (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,devices)
                or not REQUIRED<=set(r['files']) or any(pilot.sha(folder/n)!=h for n,h in r['files'].items())):
                raise ValueError('Native clock-drive task/raw/deck evidence changed')
            requested={'v('+n.replace(':','.').lower()+')' for d in devices for n in d['terminals'] if n!='0'}
            validate(folder/'bench.raw',requested,26e-9)
            measured=error=None
            try:measured=pilot.measure(folder,spec,devices)
            except ValueError as e:error=str(e)
            if measured!=r['result'] or error!=r['error']:raise ValueError('Native clock-drive independent waveform measurement changed')
            bt=bm['tasks'][int(task['id'])];bf=parent/bt['id'];br=json.loads((bf/'summary.json').read_text())
            if (bt['spec']!=spec or br['task']!=bt or br['error'] is not None or not REQUIRED<=set(br['files'])
                or any(pilot.sha(bf/n)!=h for n,h in br['files'].items())
                or (bf/'bench.cir').read_text()!=pilot.original.fixture(parent,spec,bm['identity']['devices']['pair'])):
                raise ValueError('Matching single-buffer native baseline changed')
            before=pilot.original.measure(bf,spec,bm['identity']['devices']['pair'])
            if before!=br['result']:raise ValueError('Single-buffer baseline remeasurement changed')
            comparison=dict(case=task['id'],baseline_passed=before['counter_feasibility_passed'],measurement_error=error)
            if measured is not None:
                comparison.update(two_buffer_passed=measured['counter_feasibility_passed'],
                    prepare_time_change_ps=measured['prepare_time_ps']-before['prepare_time_ps'],
                    public_release_time_change_ps=measured['public_release_time_ps']-before['public_release_time_ps'],
                    baseline_terminal_peak_v=max(d['max_terminal_difference_v'] for d in before['terminal_stress']),
                    two_buffer_terminal_peak_v=max(d['max_terminal_difference_v'] for d in measured['terminal_stress']),
                    two_buffer_minimum_clock_low_voltage_margin_v=measured['minimum_clock_low_voltage_margin_v'])
            comparisons.append(comparison);rows.append(dict(task=task,result=measured,error=error))
            paths += [folder/n for n in ['summary.json',*r['files']]]+[bf/n for n in ['summary.json',*br['files']]]
        groups=pilot.baseline_verification.assess(rows);pilot.bound(out)
        paths += [Path(__file__),Path(pilot.__file__),Path(pilot.original.__file__),Path(pilot.baseline_verification.__file__),ROOT/'scripts/native_binary_raw_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in paths})
        if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Clock-drive evidence changed during verification')
        receipt=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        receipt.mkdir(parents=True,exist_ok=False)
        pilot.atomic(receipt/'summary.json',dict(identity=identity,groups=groups,matched_single_buffer_comparison=comparisons,
            all_declared_raw_waveforms_verified=True,all_profiles_passed=all(g['source_counter_feasibility_passed'] for g in groups),
            qualified_phy=False,electrical_qualification_passed=False,
            scope='Four full-duration matched SS40 native two-buffer clock-drive cases versus independently remeasured single-buffer cases; ideal shared inter-driver wires, no whole-controller RC, joint DCC first event, hardware warmup, all-PVT or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true')
    a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
