#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate a native-PFD/source-monitor isolation bench before candidate screening."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import re
from pathlib import Path
import subprocess

import numpy as np
import probe_dll_input_conditioning as old
from dll_campaign import atomic, closure
from receiver_static_diagnosis import capture_manifest
from spice_probes import ProbeNetwork
from spice_engine import command, provenance
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ('clkbuf_4', 'clkbuf_8', 'nor3_inv4', 'nor4_inv4')
PORTS = ['A', 'VGND', 'VNB', 'VPB', 'VPWR', 'X']
CELL = old.CELL


def conditioner(pdk, variant):
    """Identical, non-inverting six-port wrappers; every gate port bound by name."""
    if variant not in CANDIDATES + ('buf_4',):
        raise ValueError('Unknown bounded frontend candidate')
    kinds = [variant] if variant in ('clkbuf_4', 'clkbuf_8', 'buf_4') else [variant.split('_')[0]+'_1', 'inv_4']
    cells = ['sky130_fd_sc_hd__'+n for n in kinds]
    text = closure(pdk, cells); lines = ['.subckt lvds_slew_conditioner '+' '.join(PORTS)]
    for i, cell in enumerate(cells):
        ports = old.pins(text, cell)
        inputs = set(ports)-{'VGND', 'VNB', 'VPB', 'VPWR', 'X', 'Y'}
        expected = {'A'} if len(cells)==1 or i==1 else set('ABCD'[:int(variant[3])])
        if inputs != expected or len(set(ports)&{'X','Y'}) != 1:
            raise ValueError('PDK gate interface changed')
        mapping = {n:n for n in ['VGND','VNB','VPB','VPWR']}
        mapping.update({n:'A' if i==0 else 'MID' for n in inputs})
        mapping.update(X='X', Y='X' if i==len(cells)-1 else 'MID')
        lines.append('XG'+str(i)+' '+' '.join(mapping[n] for n in ports)+' '+cell)
    return text+'\n'+'\n'.join(lines+['.ends lvds_slew_conditioner'])+'\n'


def fast_library(native, source):
    return closure(native, ['lvds_pfd','lvds_bias'])+'\n'+closure(source, ['screen_bias','lvds_phase_area'])


def fixture(deck, q, folder, aliases, conditioned):
    line = 'XA 0 VDDD PH0 PH90 PH180 PH270 FB PD_REF BAD UP DN PB VDDIO VDDD 0 openlvds_dll_analog'
    if deck.splitlines().count(line)!=1 or deck.count(f'.include "{q}/full.spice"')!=1:
        raise ValueError('Require unchanged native phase fixture')
    deck=deck.replace(line,'XSB PB PC NC VDDIO VDDD 0 screen_bias\nXM UP DN UF DF BAD PC VDDD VSS lvds_phase_area')
    # Native fixtures use literal ground 0; bind the monitor ground explicitly.
    deck=deck.replace('PC VDDD VSS lvds_phase_area','PC VDDD 0 lvds_phase_area')
    aliases={k:('UF' if k=='UF' else 'DF' if k=='DF' else v) for k,v in aliases.items() if k!='CTRL'}
    printed=re.findall(r'(?im)^\.print tran[^\n]+',deck)
    if len(printed)!=1:raise ValueError('Unexpected print statement')
    deck=deck.replace(printed[0],'.print tran '+' '.join('V('+n+')' for n in aliases.values()))
    if conditioned:
        # The existing frozen helper installs the two matched six-port cells.
        deck=old.fixture(deck,q,folder,PORTS).replace(old.CELL,'lvds_slew_conditioner')
    else:deck=deck.replace(f'.include "{q}/full.spice"',f'.include "{folder}/library.spice"')
    return deck,aliases


def elapsed(path):
    values=re.findall(r'Total elapsed time \(seconds\)\s*=\s*([0-9.eE+-]+)',path.read_text())
    if len(values)!=1 or float(values[0])<=0:raise ValueError('Missing engine runtime')
    return float(values[0])


def prepare(parent):
    pm=old.bound(parent);q=ROOT/pm['identity']['qualification']
    qm=json.loads((q/'manifest.json').read_text());tasks={t['id']:t for t in qm['tasks']}
    native=(q/'full.spice').read_text();source_path=ROOT/qm['identity']['full_models']['layout']/'candidate.spice'
    source=source_path.read_text();pdk=Path(pm['identity']['pdk_source']['path']).read_text()
    base=fast_library(native,source)
    paths=[parent/'manifest.json',source_path,q/'manifest.json',q/'full.spice']
    references=[]
    for rise,fall in [(20,200),(200,20)]:
        for offset in [0,50,-50,150,-150]:
            name=f'slew_ss_40_{offset}ps_{rise}_{fall}';f=q/name;r=json.loads((f/'summary.json').read_text())
            old.completed(f)
            with old.admission.storage.profile():metrics=old.admission.storage.native.evaluate(q,tasks[name])
            if metrics!=r['metrics'] or r['returncode']!=0 or old.sha(f/'bench.cir.prn')!=r['waveform_sha256'] or old.sha(f/'bench.raw')!=r['raw_sha256']:
                raise ValueError('Native calibration control changed')
            references.append(dict(id='direct_'+name,original=str(f.relative_to(ROOT)),task=tasks[name],metrics=metrics,conditioned=False))
            paths += [f/n for n in ['summary.json','bench.cir','bench.raw','bench.cir.prn','ngspice.log']]
    for t in pm['tasks']:
        f=parent/t['id'];r=json.loads((f/'summary.json').read_text())
        if r['error'] is not None or r['numerically_completed'] is not True or any(old.sha(f/n)!=h for n,h in r['files'].items()) or old.measure(f,t)!=r['metrics']:
            raise ValueError('Completed buffer negative control changed')
        references.append(dict(id='buffer_'+t['id'],original=str(f.relative_to(ROOT)),task=tasks[t['id']],metrics=r['metrics'],conditioned=True))
        paths += [f/n for n in ['summary.json','bench.cir','library.spice','bench.raw','bench.cir.prn','ngspice.log','console.log']]
    code={**pm['identity']['code'],Path(__file__).name:old.sha(Path(__file__))}
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={**pm['identity']['inputs'],**{str(p.relative_to(ROOT)):old.sha(p) for p in paths}},
                  code=code,pdk_source=pm['identity']['pdk_source'],simulator=provenance(),
                  scope='Calibration only: native PFD and native shared bias with schematic area monitor/local bias. No VCDL/OTA. Full original timing and limits retained. No candidate or PHY admission.')
    out=ROOT/'build/diagnostics/dll_slew_bench'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);prepared=[]
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        bodies={'direct':base,'buf_4':base+conditioner(pdk,'buf_4')}
        for variant in CANDIDATES:bodies[variant]=base+conditioner(pdk,variant)
        for variant,body in bodies.items():
            p=out/(variant+'.spice')
            if p.exists() and p.read_text()!=body:raise ValueError('Prepared isolation model changed')
            if not p.exists():p.write_text(body)
        for ref in references:
            folder=out/ref['id'];folder.mkdir(exist_ok=True);t=ref['task'];body=bodies['buf_4' if ref['conditioned'] else 'direct']
            deck,aliases=fixture((q/t['id']/'bench.cir').read_text(),q,folder,t['aliases'],ref['conditioned'])
            ProbeNetwork(body).validate(deck,re.findall(r'V\(([^)]+)\)',re.search(r'(?im)^\.print tran[^\n]+',deck)[0]))
            for n,text in [('library.spice',body),('bench.cir',deck)]:
                p=folder/n
                if p.exists() and p.read_text()!=text:raise ValueError('Calibration fixture changed')
                if not p.exists():p.write_text(text)
            prepared.append(dict(id=ref['id'],reference=ref['original'],reference_metrics=ref['metrics'],conditioned=ref['conditioned'],
                                 spec=t['spec'],aliases=aliases,files={n:old.sha(folder/n) for n in ['bench.cir','library.spice']}))
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=prepared,qualified_phy=False,
            models={v+'.spice':old.sha(out/(v+'.spice')) for v in bodies}))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/dll_slew_bench') or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
        len(m['tasks'])!=13 or len({t['id'] for t in m['tasks']})!=13 or provenance()!=i['simulator'] or
        any(old.sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(old.sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
        old.sha(Path(i['pdk_source']['path']))!=i['pdk_source']['sha256'] or
        any(old.sha(out/n)!=h for n,h in m['models'].items()) or any(old.sha(out/t['id']/n)!=h for t in m['tasks'] for n,h in t['files'].items())):
        raise ValueError('Isolation calibration context changed')
    return m


def measure(folder,task):
    w,h=old.completed(folder)
    for alias,n in task['aliases'].items():h['V('+alias+')']=h['V('+n.upper()+')']
    metrics=old.measurement.phase(w,h,task['spec']['offset_ps'])
    if task['conditioned']:
        t=w[:,1];a=old.measurement.edges(t,old.measurement.column(w,h,'REF_FAST'));b=old.measurement.edges(t,old.measurement.column(w,h,'FDB_FAST'))
        a=a[(a>120e-9)&(a<160e-9)]
        if len(a)<15 or len(b)<15:raise ValueError('Missing conditioned clocks')
        metrics['conditioned_phase_mean_ps']=float(np.mean([b[np.argmin(abs(b-x))]-x for x in a[1:-1]])*1e12)
    ref=task['reference_metrics']
    agrees=metrics['passed']==ref['passed'] and all(abs(metrics[n]-ref[n])<=.005 for n in ['uf_mean_v','df_mean_v','filtered_area_difference_v'])
    if task['conditioned']:agrees &= abs(metrics['conditioned_phase_mean_ps']-ref['conditioned_phase_mean_ps'])<=5
    ratio=elapsed(ROOT/task['reference']/'ngspice.log')/elapsed(folder/'ngspice.log')
    return dict(metrics=metrics,class_and_waveform_agree=bool(agrees),speedup=ratio,passed=bool(agrees and ratio>=2))


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in ['bench.raw','ngspice.log','summary.json']):raise ValueError('Partial calibration retained; no retry')
        atomic(out/'state.json',dict(status='calibrating',qualified_phy=False))
        def execute(t):
            f=out/t['id'];error=None;result=None
            try:
                with lease(ROOT,priority=2,label='dll_slew_cal_'+t['id']):
                    bound(out);p=subprocess.run(command(f/'ngspice.log',f/'bench.cir'),cwd=f,capture_output=True,text=True)
                (f/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();bound(out);result=measure(f,t)
            except Exception as e:error=str(e)
            r=dict(task=t['id'],result=result,error=error,passed=error is None and result['passed'],manifest_sha256=old.sha(out/'manifest.json'),
                   files={n:old.sha(f/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (f/n).exists()})
            capture_manifest(f/'summary.json',r);return r
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);report=dict(calibration_passed=all(r['passed'] for r in rows),results=rows,qualified_phy=False,manifest_sha256=old.sha(out/'manifest.json'))
        capture_manifest(out/'summary.json',report);atomic(out/'state.json',dict(status='calibrated' if report['calibration_passed'] else 'held_use_native_bench',qualified_phy=False))
    return report


def verify(out):
    m=bound(out);rows=[];stamp=old.sha(out/'manifest.json')
    for t in m['tasks']:
        f=out/t['id'];r=json.loads((f/'summary.json').read_text())
        if (r['task']!=t['id'] or r['manifest_sha256']!=stamp or r['error'] is not None or
            set(r['files'])!={'bench.raw','bench.cir.prn','ngspice.log','console.log'} or
            any(old.sha(f/n)!=h for n,h in r['files'].items()) or measure(f,t)!=r['result'] or
            r['passed'] is not r['result']['passed']):raise ValueError('Calibration output changed or incomplete')
        rows.append(r)
    report=dict(calibration_passed=all(r['passed'] for r in rows),results=rows,qualified_phy=False,manifest_sha256=stamp)
    if report!=json.loads((out/'summary.json').read_text()):raise ValueError('Calibration aggregate changed')
    bound(out);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);a=p.parse_args()
    r=globals()[a.action](a.artifact.resolve());print(r if a.action=='prepare' else json.dumps(r,indent=2),flush=True)
