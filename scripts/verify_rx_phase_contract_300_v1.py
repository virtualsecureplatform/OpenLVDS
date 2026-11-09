#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently inspect protocol source clocks and retain all 138 RTL results."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys
import verify_rx_protocol_300_v1 as protocol

ROOT=protocol.ROOT
PARENT=ROOT/'build/diagnostics/rx_protocol_functional_300_v1/977a49966bd55b53'
VERSION='rx-protocol-source-clock-contract-witness-300-v1'
CONTEXT='rx_protocol_clock_verification_300_v1'
SCOPE=protocol.SCOPE+'; independent ideal source-waveform checks do not qualify analog clock timing'


def parent():
    i=protocol.bound(PARENT);r=json.loads((PARENT/'summary.json').read_text())
    if (json.loads((PARENT/'state.json').read_text())!=dict(status='complete',cases=138,qualified_phy=False)
            or r['passed'] is not True or r['qualified_phy'] is not False or r['scope']!=protocol.SCOPE
            or r['warmup_stop_phases']!=480 or len(r['rows'])!=138
            or [row['task'] for row in r['rows']]!=i['specs']):raise ValueError('Require complete passing 300-profile RX protocol cohort')
    for row in r['rows']:
        task=row['task'];log=(PARENT/task['id']/'run.log').read_text()
        if row['passed'] is not True or row.get('returncode')!=0:raise ValueError('Original protocol result failed')
        if task['kind']=='scan':
            if not re.search(r'^PASS 300 RX safe scan, .*mode=\s*'+str(task['mode'])+r'\s*$',log,re.M):raise ValueError('Original scan log does not reproduce')
        else:
            match=re.search(r'^PASS v3 RX warmup clock loss: 160 phases half_period=\S+ worst=\s*(\d+) cycles$',log,re.M)
            if not match or not 1<=int(match[1])<=8 or row['worst_loss_management_cycles']!=int(match[1]):raise ValueError('Original clock-loss log does not reproduce')
    return i,r


def run():
    pi,pr=parent();files=[PARENT/n for n in ('manifest.json','summary.json','state.json')]
    files += [p for p in PARENT.glob('*/*') if p.is_file()]
    files += [Path(__file__).resolve(),ROOT/'scripts/verify_rx_protocol_300_v1.py',ROOT/'tb/tb_rx_phase_contract_300_v1.v']
    inputs={**pi['inputs'],**{str(p):protocol.sha(p) for p in files}}
    specs=[dict(mhz=f,duty=d,fault=None) for f,d in itertools.product(protocol.policy.load()['requirements']['clock_test_mhz'],(.4,.5,.6))]
    specs += [dict(mhz=300,duty=.4 if fault=='phase' else .5,fault=fault) for fault in ('frequency','duty','phase')]
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs=inputs,runtime=pi['runtime'],specs=specs,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);protocol.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    protocol.atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
    try:
        top='tb_rx_phase_contract_300_v1'
        for k,s in enumerate(specs):
            folder=out/str(k);folder.mkdir();options=[f'-P{top}.MHZ={s["mhz"]}',f'-P{top}.DUTY_PERCENT={round(s["duty"]*100)}']
            if s['fault']=='frequency':options+=[f'-P{top}.MODEL_MHZ=400']
            if s['fault']=='duty':options+=[f'-P{top}.MODEL_DUTY_PERCENT=40']
            if s['fault']=='phase':options+=[f'-P{top}.BAD_COMPLEMENT=1']
            build=subprocess.run(['iverilog','-g2012','-Wall','-s',top,*options,'-o',str(folder/'test.vvp'),
                *map(str,protocol.sources()),str(ROOT/'tb/tb_rx_phase_contract_300_v1.v')],capture_output=True,text=True,timeout=60)
            (folder/'compile.log').write_text(build.stdout+build.stderr);build.check_returncode()
            p=subprocess.run(['vvp',str(folder/'test.vvp')],capture_output=True,text=True,timeout=30)
            log=p.stdout+p.stderr;(folder/'run.log').write_text(log)
            m=re.search(r'^PASS 300 RX phase contract mhz=(\d+) duty_percent=(\d+) root_cycles=32 min_phase_rises=(\d+) period_ns=([\d.]+) high_ns=([\d.]+) phase90_ns=([\d.]+) phase180_ns=([\d.]+) phase270_ns=([\d.]+)$',log,re.M)
            if s['fault'] is not None:
                ok=bool(p.returncode!=0 and 'CLOCK CONTRACT '+s['fault'].replace('frequency','period') in log)
                row=dict(spec=s,negative_control_rejected=ok,passed=ok)
            else:
                period=1000/s['mhz'];ok=bool(p.returncode==0 and m and int(m[1])==s['mhz'] and int(m[2])==round(s['duty']*100)
                    and int(m[3])>=31 and abs(float(m[4])-period)<=.003 and abs(float(m[5])-period*s['duty'])<=.003
                    and all(abs(float(m[6+j])-period*(j+1)/4)<=.003 for j in range(3)))
                row=dict(spec=s,passed=ok,measured_period_ns=float(m[4]) if m else None,
                    measured_high_ns=float(m[5]) if m else None,measured_quarter_offsets_ns=[float(m[6+j]) for j in range(3)] if m else None)
            rows.append(row)
        parent()
        if any(protocol.sha(Path(n))!=h for n,h in inputs.items()):raise ValueError('RX clock/protocol evidence changed during verification')
        passed=all(r['passed'] for r in rows)
        protocol.atomic(out/'summary.json',dict(passed=passed,clock_rows=rows,protocol_cases=138,scan_cases=135,
            warmup_stop_phases=480,all_original_protocol_logs_reproduced=True,analog_clock_admitted=False,
            delay_model_admitted=False,qualified_phy=False,scope=SCOPE))
        protocol.atomic(out/'state.json',dict(status='complete' if passed else 'failed',qualified_phy=False))
        if not passed:raise ValueError('Source clock contract or negative control failed')
    except Exception as exc:
        protocol.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':print(run(),flush=True)
