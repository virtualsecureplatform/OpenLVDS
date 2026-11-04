#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently regenerate and remeasure isolated native NAND RC experiments."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_nand_shunt_rc_v2 as pilot
from verify_dcc_static_pilots_v4 import same
from probe_digital_dcc_v2 import sha

ROOT=pilot.ROOT
VERSION='independent-shunted-nand-native-rc-raw-verification-v2.1'


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);i=m['identity'];state=json.loads((out/'state.json').read_text())
        if state['status']!='native_gate_pilot_complete' or state['cases']!=len(m['tasks']) or state['errors']:
            raise ValueError('Require a complete numerical-error-free native gate cohort')
        gates,_=pilot.witnesses(ROOT/i['parent']);summary=json.loads((out/'summary.json').read_text())
        if len(summary['rows'])!=len(m['tasks']) or set(m['libraries'])!={n+'.spice' for n in gates}:
            raise ValueError('Incomplete native gate matrix/library set')
        devices={};files=[out/n for n in ['manifest.json','summary.json','state.json']]
        for name,g in gates.items():
            path=out/(name+'.spice')
            if path.read_text()!=g['text'] or g['info']!=i['gates'][name]:raise ValueError('Changed native RC copy/receipt')
            devices[name]=pilot.mapped_mos(g['text'],dict(A='A',B='B',Y='Y',VPWR='VDD',VGND='0'),'XG');files.append(path)
        if devices!=i['devices']:raise ValueError('Native gate terminal coverage changed')
        rows=[]
        for n,task in enumerate(m['tasks']):
            folder=out/str(n);row=json.loads((folder/'summary.json').read_text());spec=task['spec'];name=spec['macro']
            if row!=summary['rows'][n] or row['task']!=task or row['error'] is not None:raise ValueError('Native gate task/aggregate mismatch')
            if (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,gates[name],devices[name]):raise ValueError('Native gate deck regeneration changed')
            for item in ['bench.cir','bench.raw']:
                if sha(folder/item)!=row['files'][item]:raise ValueError('Native gate raw/deck changed')
            result=pilot.analyze(folder,spec,devices[name])
            if not same(result,row['result']):raise ValueError('Native gate remeasurement disagrees')
            rows.append(dict(id=task['id'],spec=spec,event_integrity_passed=result['event_integrity_passed'],
                terminal_screen_passed=result['terminal_screen_passed'],passed=result['pilot_passed'],
                propagation_delay_range_ps=result['propagation_delay_range_ps'],
                terminal_abs_peak_v=max(d['max_terminal_difference_v'] for d in result['terminal_stress']),qualified_phy=False))
            files += [folder/n for n in ['summary.json','bench.cir','bench.raw']]
        pilot.bound(out);witnesses={str(p.relative_to(ROOT)):sha(p) for p in files}
        code=[Path(__file__),Path(pilot.__file__),ROOT/'scripts/verify_dcc_static_pilots_v4.py',ROOT/'scripts/continuous_clock_conditioner_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),witnesses=witnesses,code={str(p.relative_to(ROOT)):sha(p) for p in code})
        receipt=ROOT/'build/diagnostics/nand_shunt_native_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        body=json.dumps(dict(identity=identity,rows=rows,cases=len(rows),passed=all(r['passed'] for r in rows),qualified_phy=False,
            scope='Exact native RC/deck/terminal reconstruction and independent raw remeasurement of isolated gates only; no integrated DCC or physical clock admission'),indent=2)+'\n'
        if any(sha(ROOT/n)!=h for n,h in witnesses.items()):raise ValueError('Native gate witness changed during verification')
        receipt.mkdir(parents=True,exist_ok=True);path=receipt/'summary.json'
        if path.exists() and path.read_text()!=body:raise ValueError('Retain previous native gate verification')
        if not path.exists():path.write_text(body)
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
