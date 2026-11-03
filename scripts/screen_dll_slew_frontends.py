#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Gate a bounded SS40 frontend search on completed isolation calibration."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import calibrate_dll_slew_bench as cal
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
OFFSETS=(-150,-50,-20,0,20,50,150)
SLEWS=((20,200),(200,20))
sha=cal.old.sha


def tasks():
    return [dict(id=f'{v}_{sr}_{sf}_{offset}ps',variant=v,
                 spec=dict(kind='phase',process='ss',temperature=40,mhz=400,offset_ps=offset,
                           reference_slew_ps=sr,feedback_slew_ps=sf))
            for v,(sr,sf),offset in itertools.product(cal.CANDIDATES,SLEWS,OFFSETS)]


def calibration_gate(parent):
    m=cal.bound(parent)
    if not (parent/'summary.json').is_file():raise ValueError('Complete calibration before screening')
    with (parent/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        r=json.loads((parent/'summary.json').read_text());stamp=sha(parent/'manifest.json')
        if (r['manifest_sha256']!=stamp or [x['task'] for x in r['results']]!=[t['id'] for t in m['tasks']] or
            any(x['manifest_sha256']!=stamp or any(sha(parent/x['task']/n)!=h for n,h in x['files'].items()) for x in r['results']) or
            r['calibration_passed'] is not all(x['passed'] for x in r['results'])):
            raise ValueError('Calibration receipt changed')
        if all(x['error'] is None for x in r['results']):cal.verify(parent)
        elif r['calibration_passed']:raise ValueError('Failed calibration cannot admit isolation bench')
        view='isolation' if r['calibration_passed'] else 'native'
    return m,view


def areas(lef):
    result={}
    for v in cal.CANDIDATES:
        cells=[v] if v.startswith('clkbuf') else [v.split('_')[0]+'_1','inv_4']
        total=0.
        for cell in cells:
            name='sky130_fd_sc_hd__'+cell
            match=re.search(r'(?ms)^MACRO\s+'+re.escape(name)+r'\s.*?\bSIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;',lef)
            if not match:raise ValueError('Missing PDK cell footprint: '+name)
            total+=float(match[1])*float(match[2])
        result[v]=2*total
    return result


def prepare(parent):
    cm,view=calibration_gate(parent)
    pm=cal.old.bound(ROOT/cm['identity']['parent']);q=ROOT/pm['identity']['qualification']
    qm=json.loads((q/'manifest.json').read_text());native=(q/'full.spice').read_text()
    pdk=Path(cm['identity']['pdk_source']['path']);lef=pdk.parent.parent/'lef/sky130_fd_sc_hd.lef'
    footprints=areas(lef.read_text());pdktext=pdk.read_text()
    base=cal.fast_library(native,(ROOT/qm['identity']['full_models']['layout']/'candidate.spice').read_text()) if view=='isolation' else native
    inputs=dict(cm['identity']['inputs'])
    paths=[parent/'manifest.json',parent/'summary.json',q/'manifest.json',q/'full.spice']
    for t in cm['tasks']:
        f=parent/t['id'];r=json.loads((f/'summary.json').read_text());paths += [f/'summary.json']+[f/n for n in r['files']]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code={**cm['identity']['code'],Path(__file__).name:sha(Path(__file__))}
    identity=dict(calibration=str(parent.relative_to(ROOT)),view=view,inputs=inputs,code=code,
        simulator=provenance(),pdk_source=cm['identity']['pdk_source'],lef=dict(path=str(lef),sha256=sha(lef)),
        footprint_um2=footprints,scope='SS40 400 MHz bounded four-candidate source screen. Both 20/200 and 200/20 ps slew; 0, +/-20, +/-50, +/-150 ps phase. Original health limits plus zero-balance and clock-integrity guards. Native PFD/bias; calibrated isolation monitor only if independently admitted. No physical, all-PVT, loop or PHY admission.')
    out=ROOT/'build/diagnostics/dll_slew_screen'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);prepared=[]
    template=(q/'slew_ss_40_0ps_20_200/bench.cir').read_text()
    prefix=template[:template.index('XB PB NB VDDIO 0 lvds_bias')]
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for t in tasks():
            f=out/t['id'];f.mkdir(exist_ok=True);lib=base+cal.conditioner(pdktext,t['variant'])
            body,aliases,stop,timing=cal.old.admission.storage.native.phase_fixture(t['spec'],qm['identity']['full_models']['observation_nodes'])
            if stop!=160 or timing!={'start_ns':120,'end_ns':160}:raise ValueError('Phase fixture timing changed')
            deck=prefix+body+'.save i(VA) i(VD)\n.tran 5p 160n 0 20p\n.print tran '+' '.join('V('+n+')' for n in aliases.values())+'\n.end\n'
            if view=='isolation':deck,aliases=cal.fixture(deck,q,f,aliases,True)
            else:deck=cal.old.fixture(deck,q,f,cal.PORTS).replace(cal.old.CELL,'lvds_slew_conditioner')
            ProbeNetwork(lib).validate(deck,re.findall(r'V\(([^)]+)\)',re.search(r'(?im)^\.print tran[^\n]+',deck)[0]))
            for n,text in [('library.spice',lib),('bench.cir',deck)]:
                p=f/n
                if p.exists() and p.read_text()!=text:raise ValueError('Prepared screen changed')
                if not p.exists():p.write_text(text)
            prepared.append(dict(t,aliases=aliases,files={n:sha(f/n) for n in ['bench.cir','library.spice']}))
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=prepared,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/dll_slew_screen') or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
        [{k:v for k,v in t.items() if k not in ['aliases','files']} for t in m['tasks']]!=tasks() or
        provenance()!=i['simulator'] or i['view'] not in ['isolation','native'] or
        any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
        any(sha(Path(i[n]['path']))!=i[n]['sha256'] for n in ['lef','pdk_source']) or
        any(sha(out/t['id']/n)!=h for t in m['tasks'] for n,h in t['files'].items())):raise ValueError('Screen context changed')
    return m


def clock_integrity(t,signals):
    for source,target in [('REF','REF_FAST'),('FDB','FDB_FAST')]:
        for rising in [True,False]:
            ref=cal.old.measurement.edges(t,signals[source],rising=rising)
            out=cal.old.measurement.edges(t,signals[target],rising=rising)
            ref=ref[(ref>125e-9)&(ref<155e-9)]
            if len(ref)<10:return False
            matched=[]
            for x in ref:
                hits=np.flatnonzero(abs(out-x)<1.25e-9)
                if len(hits)!=1:return False
                matched.append(int(hits[0]))
            if len(set(matched))!=len(ref):return False
        keep=(t>120e-9)&(t<160e-9)
        if signals[target][keep].min()>.36 or signals[target][keep].max()<1.44:return False
    return True


def measure(folder,task):
    w,h=cal.old.completed(folder)
    for alias,n in task['aliases'].items():h['V('+alias+')']=h['V('+n.upper()+')']
    metrics=cal.old.measurement.phase(w,h,task['spec']['offset_ps']);t=w[:,1]
    signals={n:cal.old.measurement.column(w,h,n) for n in ['REF','FDB','REF_FAST','FDB_FAST']}
    integrity=clock_integrity(t,signals)
    names,raw=read_raw(folder/'bench.raw');keep=(t>120e-9)&(t<160e-9)
    power=-3.3*raw[:,names.index('i(va)')]-1.8*raw[:,names.index('i(vd)')]
    return dict(phase=metrics,clock_integrity_passed=bool(integrity),mean_power_w=cal.old.measurement.average(t[keep],power[keep]),passed=bool(metrics['passed'] and integrity))


def aggregate(out,m,rows):
    candidates=[]
    for v in cal.CANDIDATES:
        selected=[r for r in rows if r['variant']==v];errors=[];zeros=[];power=[]
        valid=len(selected)==14 and all(r['error'] is None and r['result'] and r['result']['passed'] for r in selected)
        for sr,sf in SLEWS:
            group={r['offset_ps']:r['result'] for r in selected if r['slew']==[sr,sf] and r['result']}
            if set(group)!=set(OFFSETS):valid=False;continue
            delta=[group[n]['phase']['filtered_area_difference_v'] for n in OFFSETS]
            monotonic=all(b>a for a,b in zip(delta,delta[1:]));lo=group[-20]['phase']['filtered_area_difference_v'];hi=group[20]['phase']['filtered_area_difference_v']
            balance=lo<0<hi
            valid=valid and monotonic and balance
            if balance:zeros.append(float(-20+40*(-lo)/(hi-lo)))
            errors.append(dict(slew=[sr,sf],monotonic=monotonic,zero_bracket_passed=balance))
            power.extend(g['mean_power_w'] for g in group.values())
        candidates.append(dict(variant=v,passed=bool(valid),checks=errors,estimated_zero_offset_max_abs_ps=max(map(abs,zeros)) if len(zeros)==2 else None,
            mean_power_w=float(np.mean(power)) if power else None,cell_area_um2=m['identity']['footprint_um2'][v]))
    eligible=[r for r in candidates if r['passed']];rank=[]
    while eligible:
        best=min(r['estimated_zero_offset_max_abs_ps'] for r in eligible)
        tie=[r for r in eligible if r['estimated_zero_offset_max_abs_ps']<=best+2]
        chosen=min(tie,key=lambda r:(r['mean_power_w'],r['cell_area_um2'],cal.CANDIDATES.index(r['variant'])))
        rank.append(chosen['variant']);eligible.remove(chosen)
    return dict(candidates=candidates,ranked_survivors=rank,results=rows,qualified_phy=False,physical_admission=False,
                manifest_sha256=sha(out/'manifest.json'),scope=m['identity']['scope'])


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    def unchanged():
        if sha(out/'manifest.json')!=stamp:raise ValueError('Screen manifest changed during execution')
        bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in ['bench.raw','ngspice.log','summary.json']):raise ValueError('Partial screen retained; no retry')
        atomic(out/'state.json',dict(status='screening',qualified_phy=False))
        def execute(t):
            f=out/t['id'];result=None;error=None
            try:
                with lease(ROOT,priority=2,label='dll_slew_screen_'+t['id']):
                    unchanged();p=subprocess.run(command(f/'ngspice.log',f/'bench.cir'),cwd=f,capture_output=True,text=True)
                (f/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();unchanged();result=measure(f,t);unchanged()
            except Exception as e:error=str(e)
            r=dict(task=t['id'],variant=t['variant'],offset_ps=t['spec']['offset_ps'],slew=[t['spec']['reference_slew_ps'],t['spec']['feedback_slew_ps']],
                   result=result,error=error,manifest_sha256=stamp,files={n:sha(f/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (f/n).exists()})
            capture_manifest(f/'summary.json',r);return r
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        unchanged();report=aggregate(out,m,rows);capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='screened' if report['ranked_survivors'] else 'held_no_survivor',qualified_phy=False))
    return report


def verify(out):
    m=bound(out);rows=[]
    for t in m['tasks']:
        f=out/t['id'];r=json.loads((f/'summary.json').read_text())
        if (r['task']!=t['id'] or r['variant']!=t['variant'] or r['offset_ps']!=t['spec']['offset_ps'] or
            r['slew']!=[t['spec']['reference_slew_ps'],t['spec']['feedback_slew_ps']] or r['error'] is not None or
            r['manifest_sha256']!=sha(out/'manifest.json') or set(r['files'])!={'bench.raw','bench.cir.prn','ngspice.log','console.log'} or
            any(sha(f/n)!=h for n,h in r['files'].items()) or measure(f,t)!=r['result']):raise ValueError('Screen output changed')
        rows.append(r)
    report=aggregate(out,m,rows)
    if report!=json.loads((out/'summary.json').read_text()):raise ValueError('Screen aggregate changed')
    bound(out);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);a=p.parse_args()
    r=globals()[a.action](a.artifact.resolve());print(r if a.action=='prepare' else json.dumps(r,indent=2),flush=True)
