#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture the pinned divider-12 RTL/controller in a separate 300 MHz namespace."""
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
import clocking_profile_300 as policy
import openpll_clock as legacy
from check_openpll_contract import metrics
ROOT=policy.ROOT

def run():
    profile=policy.load();out=ROOT/'build/openpll_300'
    pin=subprocess.check_output(['git','-C',str(ROOT/'thirdparties/OpenPLL'),'rev-parse','HEAD'],text=True).strip()
    if pin!=profile['requirements']['openpll_commit']:raise ValueError('Unexpected OpenPLL revision')
    sources=legacy.rtl_sources()[:-2]+[ROOT/'examples/openlvds_openpll_300.v',ROOT/'tb/tb_openpll_300.v']
    out.mkdir(parents=True,exist_ok=False)
    paths=[Path(__file__),ROOT/'scripts/clocking_profile_300.py',ROOT/'scripts/openpll_clock.py',
           ROOT/'scripts/check_openpll_contract.py',ROOT/'clocking_300mhz.json',*sources]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={str(p.relative_to(ROOT)):sha(p) for p in paths}
    (out/'manifest.json').write_text(json.dumps(dict(inputs=inputs,openpll_commit=pin,qualified_phy=False),indent=2)+'\n')
    compile_command=['iverilog','-g2012','-Wall','-DOPENPLL_DCO_MODEL_COARSE','-s','tb_openpll_300','-o',str(out/'pll.vvp'),*map(str,sources)]
    for command,name in [(compile_command,'compile.log'),(['vvp',str(out/'pll.vvp')],'simulation.log')]:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        (out/name).write_text(result.stdout+result.stderr)
        result.check_returncode()
    wave=np.loadtxt(out/'clock.csv',delimiter=',',skiprows=1)
    measured=metrics(wave,profile['requirements'])
    if any(sha(ROOT/n)!=digest for n,digest in inputs.items()):raise ValueError('Clock source/profile changed during simulation')
    report=dict(metrics=measured,inputs=inputs,clock_sha256=sha(out/'clock.csv'),openpll_commit=pin,
        profile_sha256=sha(ROOT/'clocking_300mhz.json'),qualified_phy=False,
        scope='300MHz pinned OpenPLL RTL/controller with calibrated behavioral DCO and behavioral BBPD; no extracted or closed-loop physical jitter qualification')
    (out/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(measured,indent=2),flush=True)
    if not measured['passed']:raise ValueError('300MHz clock contract failed')
    return out
if __name__=='__main__':run()
