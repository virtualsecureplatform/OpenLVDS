#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Four short, diagnostic-only TX boundary/RC experiments; never qualify a PHY."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl,hashlib,json,re,subprocess
from pathlib import Path
import numpy as np
from dll_campaign import atomic,text_block
from exact_rc_candidate import parse,static_signature
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command,provenance
from spice_library import replace
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_tx_core'
CASES=['tx_reduced','tx_raw','coupled_reduced','coupled_raw']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def fixture(text,library,old,new,tx_only):
    includes=re.findall(r'(?im)^\.include[^\n]+',text)
    if includes!=[f'.include "{old}/library.spice"']:raise ValueError('Unexpected library inclusion')
    trans=re.findall(r'(?im)^\.tran[^\n]+',text)
    if len(trans)!=1 or trans[0].split()[1:]!=['20p','188.049n','0','1p']:raise ValueError('Require unchanged full diagnostic as parent')
    if tx_only:
        instances=[s for s in text.splitlines() if re.match(r'^XTX\s',s,re.I)]
        if len(instances)!=1:raise ValueError('Require exactly one native TX')
        # Native TX header may continue across lines.
        h=re.search(r'(?im)^\.subckt '+TOP+r'[^\n]*(?:\n\+[^\n]*)*',library)[0].replace('\n+',' ').split()[2:]
        tokens=instances[0].split();mapping=dict(zip(h,tokens[1:-1],strict=True))
        if tokens[-1]!=TOP:raise ValueError('Unexpected TX instance model')
        rows=['OpenLVDS TX-only convergence isolation']
        rows += [s for s in text.splitlines()[1:] if re.match(r'(?i)^(?:\.lib\s|\.options\s|V\S+\s)',s)]
        rows += [f'.include "{new}/library.spice"',instances[0]]
        rows += [f'CISO{i} {mapping[n]} 0 100f' for i,n in enumerate(['tx_serial','forwarded_clock'])]
        text='\n'.join(rows)+'\n.tran 1p 12n 0 1p\n'
        probes=list(dict.fromkeys(mapping.values()))
    else:
        text=text.replace(includes[0],f'.include "{new}/library.spice"').replace(trans[0],'.tran 1p 12n 0 1p')
        printed=re.findall(r'(?im)^\.print tran[^\n]+',text)
        if len(printed)!=1:raise ValueError('Require one original print statement')
        probes=re.findall(r'V\(([^)]+)\)',printed[0],re.I)
        text=text.replace(printed[0],'');text=re.sub(r'(?im)^\.end\s*$','',text)
    probes += ['XTX:'+n for n in ['VGND.t436','VGND.t435','VGND.t434','VGND.n5812','VGND.t522','VPWR.t549']]
    text += '.print tran '+' '.join('V('+p+')' for p in probes)+'\n.end\n'
    ProbeNetwork(library).validate(text,probes)
    return text


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_feedback_link_diagnostic'):raise ValueError('Require isolated coupled diagnostic')
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if i.get('diagnostic_only') is not True or i.get('maximum_step_ps')!=1 or 'newton_budget' in i:raise ValueError('Require original one-ps diagnostic')
    for name,h in i['inputs'].items():
        if sha(ROOT/name)!=h:raise ValueError('Parent input changed')
    for name,h in i['code'].items():
        if sha(ROOT/'scripts'/name)!=h:raise ValueError('Parent producer changed')
    for name,h in m['files'].items():
        if sha(parent/name)!=h:raise ValueError('Parent fixture changed')
    physical=ROOT/'build/diagnostics/tx_buffer4_physical';info=json.loads((physical/'extraction.json').read_text())
    raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist'];base=(parent/'library.spice').read_text()
    if sha(reduced)!=info['netlist_sha256'] or sha(raw)!=info['reduction']['source_sha256'] or text_block(base,TOP)!=text_block(reduced.read_text(),TOP):raise ValueError('TX extraction binding changed')
    if static_signature(parse(raw.read_text()))!=static_signature(parse(reduced.read_text())):raise ValueError('Raw/reduced TX changes device or capacitor statements')
    paths=[parent/'manifest.json',parent/'bench.cir',parent/'library.spice',physical/'extraction.json',raw,reduced]
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code={n:sha(ROOT/'scripts'/n) for n in [Path(__file__).name,'run_ngspice.py','spice_dispatch.py','spice_library.py','spice_probes.py','exact_rc_candidate.py','receiver_static_diagnosis.py','dll_campaign.py','spice_engine.py']},
        simulator=provenance(),scope='12 ns boundary/RC isolation only. Same supplies, source stimuli and accuracy; one ps maximum step. TX-only uses 100 fF per output. Raw/reduced preserve all device/capacitor statements. No component or PHY admission.')
    out=ROOT/'build/diagnostics/tx_convergence_isolation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    tasks=[]
    for case in CASES:
        folder=out/case;folder.mkdir(exist_ok=True)
        library=replace(base,TOP,text_block(raw.read_text(),TOP)) if case.endswith('_raw') else base
        deck=fixture((parent/'bench.cir').read_text(),library,parent,folder,case.startswith('tx_'))
        for name,body in [('library.spice',library),('bench.cir',deck)]:
            p=folder/name
            if p.exists() and p.read_text()!=body:raise ValueError('Prepared isolation context changed')
            if not p.exists():p.write_text(body)
        tasks.append(dict(id=case,files={n:sha(folder/n) for n in ['library.spice','bench.cir']}))
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/tx_convergence_isolation'):raise ValueError('Require isolated TX convergence context')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    if out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]:raise ValueError('Isolation identity changed')
    if [t['id'] for t in m['tasks']]!=CASES or any(set(t['files'])!={'bench.cir','library.spice'} for t in m['tasks']):raise ValueError('Require all four exact isolation cases')
    def unchanged():
        if sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Isolation context changed')
    def execute(task):
        folder=out/task['id'];unchanged()
        for n,h in task['files'].items():
            if sha(folder/n)!=h:raise ValueError('Isolation fixture changed')
        if any((folder/n).exists() for n in ['bench.raw','summary.json','ngspice.log']):raise ValueError('Prior isolation output retained')
        atomic(folder/'state.json',dict(status='waiting_for_slot'))
        with lease(ROOT,priority=2,label='tx_isolation_'+task['id']):
            unchanged();atomic(folder/'state.json',dict(status='running'))
            p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
        (folder/'console.log').write_text(p.stdout+p.stderr);unchanged()
        complete=False
        if p.returncode==0:
            names,w=read_raw(folder/'bench.raw');t=w[:,names.index('time')]
            complete=bool(np.isfinite(w).all() and np.all(np.diff(t)>0) and t[0]<=1e-15 and t[-1]>=12e-9-1e-12)
        log=(folder/'ngspice.log').read_text();failure=re.search(r'Timestep too small;[^\n]+',log)
        result=dict(task=task['id'],numerically_completed=complete,returncode=p.returncode,failure=failure[0] if failure else None,electrical_verdict=None,qualified_phy=False,manifest_sha256=stamp,files={n:sha(folder/n) for n in ['bench.cir','library.spice','ngspice.log','console.log','bench.raw'] if (folder/n).exists()})
        capture_manifest(folder/'summary.json',result);return result
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior isolation run retained')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,m['tasks']))
        capture_manifest(out/'summary.json',dict(results=results,qualified_phy=False,manifest_sha256=stamp,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_isolation',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
