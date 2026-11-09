#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check RX warmup clock-loss deadline with both frozen levels at the new profile."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys
import verify_rx_protocol_300_v1 as protocol
import verify_rx_phase_contract_300_v2 as clocks

ROOT=protocol.ROOT
CLOCK_PROOF=ROOT/'build/diagnostics/rx_protocol_clock_verification_300_v2/920c2f6d766c7faf'
VERSION='rx-frozen-delivered-clock-level-loss-protocol-300-v1'
CONTEXT='rx_frozen_clock_loss_300_v1'
SCOPE='Real RX startup/watch/failure RTL and HDL DCCs with ideal source phases, synthetic backend and supplied DLL lock; no native clock, physical eye, actual DLL or PHY admission'


def generator(text):
    return [line for line in text.splitlines() if line.startswith(('    initial begin #(PERIOD','    localparam real PERIOD='))]


def run():
    pi,_=clocks.parent();m=json.loads((CLOCK_PROOF/'manifest.json').read_text());r=json.loads((CLOCK_PROOF/'summary.json').read_text())
    ci=m['identity']
    if (ci['version']!=clocks.VERSION or CLOCK_PROOF.name!=hashlib.sha256(json.dumps(ci,sort_keys=True).encode()).hexdigest()[:16]
            or json.loads((CLOCK_PROOF/'state.json').read_text())!=dict(status='complete',qualified_phy=False)
            or r['passed'] is not True or r['qualified_phy'] is not False or len(r['clock_rows'])!=12
            or not all(row['passed'] for row in r['clock_rows'])
            or any(protocol.sha(Path(n))!=h for n,h in ci['inputs'].items())):
        raise ValueError('Require complete source-clock/profile proof')
    bench=ROOT/'tb/tb_rx_frozen_clock_loss_300_v1.v'
    if generator(bench.read_text())!=generator((ROOT/'tb/tb_rx_training_300_v1.v').read_text()):
        raise ValueError('Frozen-loss source waveform generator differs from proved protocol clocks')
    paths=[Path(__file__).resolve(),bench,*protocol.sources(),CLOCK_PROOF/'manifest.json',CLOCK_PROOF/'summary.json',CLOCK_PROOF/'state.json']
    paths += [p for p in CLOCK_PROOF.glob('*/*') if p.is_file()]
    inputs={**ci['inputs'],**{str(p):protocol.sha(p) for p in paths}}
    req=protocol.policy.load()['requirements'];specs=[dict(mhz=f,duty=d) for f,d in itertools.product(req['clock_test_mhz'],req['clock_duty'])]
    identity=dict(version=VERSION,inputs=inputs,clock_proof=str(CLOCK_PROOF.relative_to(ROOT)),runtime=pi['runtime'],specs=specs,max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);protocol.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    protocol.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    def one(item):
        k,s=item;folder=out/str(k);folder.mkdir();top='tb_rx_frozen_clock_loss_300_v1'
        build=subprocess.run(['iverilog','-g2012','-Wall','-s',top,f'-P{top}.MHZ={s["mhz"]}',
            f'-P{top}.DUTY_PERCENT={round(s["duty"]*100)}','-o',str(folder/'test.vvp'),*map(str,protocol.sources()),str(bench)],
            capture_output=True,text=True,timeout=60)
        (folder/'compile.log').write_text(build.stdout+build.stderr)
        if build.returncode:return dict(spec=s,passed=False,error='Compilation failed')
        p=subprocess.run(['vvp',str(folder/'test.vvp')],capture_output=True,text=True,timeout=60)
        log=p.stdout+p.stderr;(folder/'run.log').write_text(log)
        m=re.search(r'^PASS 300 RX frozen-clock loss: mhz=(\d+) duty_percent=(\d+) phases=160 worst=(\d+) low0=(\d+) high0=(\d+) low90=(\d+) high90=(\d+)$',log,re.M)
        counts=[int(m[k]) for k in (4,5,6,7)] if m else []
        ok=bool(p.returncode==0 and m and int(m[1])==s['mhz'] and int(m[2])==round(s['duty']*100)
            and 1<=int(m[3])<=8 and all(n>0 for n in counts) and sum(counts[:2])==sum(counts[2:])==80)
        return dict(spec=s,passed=ok,returncode=p.returncode,stop_phases=160 if m else 0,
            worst_loss_management_cycles=int(m[3]) if m else None,held_level_counts=counts)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,enumerate(specs)))
        if any(protocol.sha(Path(n))!=h for n,h in inputs.items()):raise ValueError('Frozen-loss inputs changed during regression')
        passed=bool(len(rows)==9 and all(row['passed'] for row in rows))
        protocol.atomic(out/'summary.json',dict(rows=rows,passed=passed,stop_phases=sum(row['stop_phases'] for row in rows),
            native_clock_admitted=False,delay_model_admitted=False,qualified_phy=False,scope=SCOPE))
        protocol.atomic(out/'state.json',dict(status='complete' if passed else 'failed',qualified_phy=False))
        if not passed:raise ValueError('Frozen-clock eight-management-cycle loss regression failed')
    except Exception as exc:
        protocol.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':print(run(),flush=True)
