#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate and independently remeasure all joint static-release DCC cases."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_native_static_dcc_v2 as pilot
from verify_conditioned_clock_v2 import compare_result
from probe_digital_dcc_v2 import sha

ROOT=pilot.ROOT
VERSION='independent-joint-static-phase-release-native-dcc-verification-v2.1'


def regenerate(out):
    m=pilot.bound(out);i=m['identity']
    modules,devices,_,pdk,variant,artifacts=pilot.assembly(ROOT/i['parent'],ROOT/i['profile'],ROOT/i['tg'])
    if (set(modules)!=set(m['libraries']) or any((out/n).read_text()!=text for n,text in modules.items())
        or devices!=i['devices'] or pdk!=i['pdk_files'] or variant!=i['selected_counter']
        or [str(p.relative_to(ROOT)) for p in artifacts]!=i['components']):raise ValueError('Joint static DCC regeneration changed')
    return m,devices


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m,devices=regenerate(out);state=json.loads((out/'state.json').read_text());summary=json.loads((out/'summary.json').read_text())
        if (state['status']!='joint_static_dcc_complete' or state['cases']!=len(m['tasks'])
            or state['errors'] or len(summary['rows'])!=len(m['tasks'])):raise ValueError('Require all numerically complete joint cases')
        files=[out/n for n in ['manifest.json','summary.json','state.json',*m['libraries']]];rows=[]
        for n,task in enumerate(m['tasks']):
            folder=out/str(n);r=json.loads((folder/'summary.json').read_text());spec=task['spec'];ds=devices[spec['variant']]
            if (r!=summary['rows'][n] or r['task']!=task or r['error'] is not None
                or (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,ds)
                or not {'bench.cir','bench.raw','ngspice.log','console.log','bench.ngspice.cir'}<=set(r['files'])
                or any(sha(folder/name)!=h for name,h in r['files'].items())):raise ValueError('Joint case/deck/raw witness changed')
            measured=pilot.measure(folder,spec,ds,'Independent joint static DCC remeasurement');compare_result(measured,r['result'])
            keys=['startup_passed','event_integrity_passed','prepare_before_public_mask_passed',
                  'reset_after_three_clock_edges_passed','common_mode_passed','half_cycle_passed','terminal_screen_passed']
            rows.append(dict(id=task['id'],spec=spec,passed=measured['pilot_passed'],
                requirements={k:measured[k] for k in keys},mean_half_cycle_error_ps=measured['half_cycle_error_ps'],
                low_voltage_terminal_peak_v=max(d['max_terminal_difference_v'] for d in measured['terminal_stress'] if d['limit_v']==1.95),qualified_phy=False))
            files += [folder/name for name in ['summary.json',*r['files']]]
        pilot.bound(out)
        code=[Path(__file__),Path(pilot.__file__),Path(pilot.components.__file__),ROOT/'scripts/measure_native_static_dcc_v2.py',ROOT/'scripts/verify_conditioned_clock_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files+code})
        receipt=ROOT/'build/diagnostics/native_static_dcc_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        body=json.dumps(dict(identity=identity,rows=rows,passed=all(r['passed'] for r in rows),qualified_phy=False,
            scope='Complete four-case SS40 component-RC DCC/static-release pilot; source analog conditioner, ideal common wires and no full-PVT/whole-backend/PHY admission'),indent=2)+'\n'
        if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Joint witness changed during verification')
        receipt.mkdir(parents=True,exist_ok=True);path=receipt/'summary.json'
        if path.exists() and path.read_text()!=body:raise ValueError('Retain prior joint receipt')
        if not path.exists():path.write_text(body)
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
