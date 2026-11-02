#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded original-model diagnostic: Sparse 1.3 versus the failed KLU solve."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from receiver_static_diagnosis import capture_manifest
from dll_campaign import atomic
from run_ngspice import read_raw
from spice_engine import command,provenance
from spice_dispatch import lease

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def fixture(deck,old,new):
    include=f'.include "{old}/library.spice"'
    if deck.count(include)!=1 or re.findall(r'(?im)^\.tran[^\n]+',deck)!=['.tran 1p 12n 0 1p']:raise ValueError('Require original twelve-ns/one-ps isolation fixture')
    if re.search(r'(?i)\b(?:sparse|klu|itl4)\b',deck):raise ValueError('Parent must use unchanged default KLU/budget policy')
    deck=deck.replace(include,f'.include "{new}/library.spice"')
    first,rest=deck.split('\n',1)
    # The frozen exporter injects KLU immediately after the title. The later
    # explicit option must override it; the run verifies the actual log.
    return first+'\n.options sparse\n'+rest


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/tx_convergence_isolation') or parent.name!='coupled_raw':raise ValueError('Use original all-device raw-RC coupled failure')
    report=json.loads((parent/'summary.json').read_text());m=json.loads((parent.parent/'manifest.json').read_text());i=m['identity']
    if report.get('numerically_completed') is not False or 'Timestep too small' not in (report.get('failure') or '') or report['manifest_sha256']!=sha(parent.parent/'manifest.json'):raise ValueError('Require bound terminal KLU timestep collapse')
    if 'Using KLU as Direct Linear Solver' not in (parent/'ngspice.log').read_text():raise ValueError('Parent did not actually use KLU')
    for n,h in report['files'].items():
        if sha(parent/n)!=h:raise ValueError('Terminal KLU evidence changed')
    for n,h in i['inputs'].items():
        if sha(ROOT/n)!=h:raise ValueError('Original model/source inputs changed')
    paths=[parent.parent/'manifest.json']+[parent/n for n in ['summary.json','bench.cir','library.spice','ngspice.log']]
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code={n:sha(ROOT/'scripts'/n) for n in ['isolate_sparse_solver.py','run_ngspice.py','spice_dispatch.py','spice_engine.py','receiver_static_diagnosis.py','dll_campaign.py']},simulator=provenance(),
        scope='One Sparse 1.3 diagnostic with all original devices, all raw TX RC and original coupled stimuli intact; same numerical tolerances, iteration budget and one-ps maximum step. No electrical or PHY admission.',
        documentation='https://ngspice.sourceforge.io/docs/ngspice-manual.pdf')
    out=ROOT/'build/diagnostics/tx_sparse_isolation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    for n,body in [('bench.cir',fixture((parent/'bench.cir').read_text(),parent,out)),('library.spice',(parent/'library.spice').read_text())]:
        p=out/n
        if p.exists() and p.read_text()!=body:raise ValueError('Prepared solver fixture changed')
        if not p.exists():p.write_text(body)
    capture_manifest(out/'manifest.json',dict(identity=identity,files={n:sha(out/n) for n in ['bench.cir','library.spice']},qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/tx_sparse_isolation'):raise ValueError('Use prepared solver isolation')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or any(sha(out/n)!=h for n,h in m['files'].items()):raise ValueError('Sparse experiment changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if any((out/n).exists() for n in ['state.json','bench.raw','ngspice.log','summary.json']):raise ValueError('Prior solver diagnostic output retained')
        atomic(out/'state.json',dict(status='waiting_for_slot',qualified_phy=False))
        with lease(ROOT,priority=2,label='sparse_original_coupled'):
            unchanged();atomic(out/'state.json',dict(status='running',qualified_phy=False))
            p=subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(p.stdout+p.stderr);unchanged();log=(out/'ngspice.log').read_text()
        selected='Using SPARSE 1.3 as Direct Linear Solver' in log and 'Using KLU as Direct Linear Solver' not in log
        complete=False
        if p.returncode==0 and selected:
            names,w=read_raw(out/'bench.raw');t=w[:,names.index('time')]
            complete=bool(np.isfinite(w).all() and t[0]<=1e-15 and t[-1]>=12e-9-1e-12 and np.all(np.diff(t)>0))
        failure=re.search(r'Timestep too small;[^\n]+',log)
        capture_manifest(out/'summary.json',dict(numerically_completed=complete,actual_sparse_solver_verified=selected,returncode=p.returncode,
            failure=failure[0] if failure else None,electrical_verdict=None,qualified_phy=False,manifest_sha256=stamp,
            files={n:sha(out/n) for n in ['bench.raw','ngspice.log','console.log'] if (out/n).exists()},scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_diagnostic',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
