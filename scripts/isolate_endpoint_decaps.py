#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Distinguish TX/RX boundary-decap effects after the TX-only removal failed."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import numpy as np
import isolate_tx_decap as mapped
from dll_campaign import text_block,atomic
from receiver_static_diagnosis import capture_manifest
from spice_library import replace
from spice_engine import command,provenance
from spice_dispatch import lease
from run_ngspice import read_raw

ROOT=Path(__file__).resolve().parents[1]
RX='openlvds_ddr_rx'
CASES=['rx_only','both_endpoints']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


@contextmanager
def rx_mapping():
    """Select the RX top and serial-pin coordinate registration only."""
    previous=mapped.TOP,mapped.registration
    register=mapped.registration
    def registration(ext,definition):
        # The original checked mapper registers tx_serial. Relabel only the
        # independent physical pin records for the same coordinate calculation.
        ext,n=re.subn(r'(?m)^port "serial"', 'port "tx_serial"',ext)
        definition,k=re.subn(r'(?m)^(\s*)- serial \+ NET serial ',r'\1- tx_serial + NET tx_serial ',definition)
        if n!=1 or k!=1:raise ValueError('Require unique RX serial physical pin registration')
        return register(ext,definition)
    try:
        mapped.TOP=RX;mapped.registration=registration
        yield
    finally:mapped.TOP,mapped.registration=previous


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/tx_decap_isolation'):raise ValueError('Use completed mapped TX-decap isolation')
    m=json.loads((parent/'manifest.json').read_text());i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if r.get('numerically_completed') is not False or 'xrx.vgnd.t215' not in (r.get('failure') or ''):raise ValueError('Require terminal collapse shifted to the native RX ground terminal')
    if r['manifest_sha256']!=sha(parent/'manifest.json'):raise ValueError('TX decap result binding changed')
    for n,h in dict(m['files'],**r['files']).items():
        if sha(parent/n)!=h:raise ValueError('TX decap evidence changed')
    for n,h in i['inputs'].items():
        if sha(ROOT/n)!=h:raise ValueError('TX decap inputs changed')
    for n,h in i['code'].items():
        if sha(ROOT/'scripts'/n)!=h:raise ValueError('TX decap producer changed')
    for n,h in i['pdk'].items():
        if sha(Path(n))!=h:raise ValueError('PDK changed')
    physical=ROOT/'build/diagnostics/rx_early_physical_v1';s=json.loads((physical/'summary.json').read_text());info=json.loads((physical/'extraction.json').read_text())
    run=ROOT/s['run'];raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist']
    if not s['passed'] or sha(raw)!=info['reduction']['source_sha256'] or sha(reduced)!=info['netlist_sha256'] or sha(run/'final/gds'/f'{RX}.gds')!=info['gds_sha256']:raise ValueError('RX physical/extraction binding changed')
    res=raw.parent/(RX+'_rcx.res.ext');ext=raw.parent/(RX+'_rcx.ext');definition=run/'final/def'/f'{RX}.def'
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd';lef=pdk/'lef/sky130_fd_sc_hd.lef';cells=pdk/'spice/sky130_fd_sc_hd.spice'
    with rx_mapping():mapping=mapped.mapped_devices(raw.read_text(),res.read_text(),definition.read_text(),lef.read_text(),cells.read_text(),ext.read_text())
    libraries={}
    baseline=ROOT/i['parent']/'coupled_raw';original=(baseline/'library.spice').read_text()
    tx_removed=(parent/'library.spice').read_text()
    if text_block(original,RX)!=text_block(reduced.read_text(),RX) or text_block(tx_removed,RX)!=text_block(original,RX):raise ValueError('Both controls require the exact original native RX')
    rx_removed=mapped.remove_mapped(text_block(reduced.read_text(),RX),mapping)
    libraries['rx_only']=replace(original,RX,rx_removed);libraries['both_endpoints']=replace(tx_removed,RX,rx_removed)
    paths=[parent/'manifest.json',parent/'summary.json',parent/'bench.cir',parent/'library.spice',baseline/'bench.cir',baseline/'library.spice',
        physical/'summary.json',physical/'extraction.json',raw,reduced,res,ext,definition,run/'final/gds'/f'{RX}.gds']
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk=i['pdk'],
        mapping=mapping,simulator=provenance(),code=dict(i['code'],**{n:sha(ROOT/'scripts'/n) for n in ['isolate_endpoint_decaps.py','isolate_tx_decap.py','run_ngspice.py','spice_engine.py','spice_dispatch.py','spice_library.py','receiver_static_diagnosis.py','dll_campaign.py']}),
        scope='Two bounded 12 ns diagnostics: mapped RX decap MOS removal only, or both endpoints. Preserve every TX/RX wire resistor/capacitor, all unrelated devices and original coupled stimuli. Never component or PHY admission.')
    out=ROOT/'build/diagnostics/endpoint_decap_isolation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True);tasks=[]
    for case in CASES:
        folder=out/case;folder.mkdir(exist_ok=True)
        deck=(baseline/'bench.cir').read_text();include=f'.include "{baseline}/library.spice"'
        if deck.count(include)!=1:raise ValueError('Unexpected original coupled fixture')
        deck=deck.replace(include,f'.include "{folder}/library.spice"')
        for name,body in [('bench.cir',deck),('library.spice',libraries[case])]:
            p=folder/name
            if p.exists() and p.read_text()!=body:raise ValueError('Prepared endpoint fixture changed')
            if not p.exists():p.write_text(body)
        tasks.append(dict(id=case,files={n:sha(folder/n) for n in ['bench.cir','library.spice']}))
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/endpoint_decap_isolation'):raise ValueError('Use mapped endpoint diagnostic')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    if [t['id'] for t in m['tasks']]!=CASES:raise ValueError('Require both endpoint isolation cases')
    def unchanged():
        if sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Endpoint diagnostic context changed')
    def execute(task):
        folder=out/task['id'];unchanged()
        if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Endpoint fixture changed')
        if any((folder/n).exists() for n in ['state.json','bench.raw','summary.json','ngspice.log']):raise ValueError('Prior endpoint diagnostic output retained')
        atomic(folder/'state.json',dict(status='waiting_for_slot',qualified_phy=False))
        with lease(ROOT,priority=2,label='endpoint_decap_'+task['id']):
            unchanged();atomic(folder/'state.json',dict(status='running',qualified_phy=False))
            p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
        (folder/'console.log').write_text(p.stdout+p.stderr);unchanged();complete=False
        if p.returncode==0:
            names,w=read_raw(folder/'bench.raw');t=w[:,names.index('time')]
            complete=bool(np.isfinite(w).all() and t[0]<=1e-15 and t[-1]>=12e-9-1e-12 and np.all(np.diff(t)>0))
        log=(folder/'ngspice.log').read_text();failure=re.search(r'Timestep too small;[^\n]+',log)
        result=dict(task=task['id'],numerically_completed=complete,returncode=p.returncode,failure=failure[0] if failure else None,electrical_verdict=None,qualified_phy=False,manifest_sha256=stamp,
            files={n:sha(folder/n) for n in ['bench.raw','ngspice.log','console.log'] if (folder/n).exists()})
        capture_manifest(folder/'summary.json',result);atomic(folder/'state.json',dict(status='completed_diagnostic',qualified_phy=False));return result
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior endpoint run retained')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,m['tasks']))
        capture_manifest(out/'summary.json',dict(results=results,manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_diagnostic',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
