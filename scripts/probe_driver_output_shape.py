#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One calculated symmetric MIM-load candidate, with both-polarity DC calibration."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
import probe_driver_gate_taper as pilot
from dll_campaign import atomic,text_block
from dll_measurements import read_wave,edges
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command,engine,provenance
from spice_library import replace
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
CASES=['negative_op','positive_op']
sha=pilot.sha


def shaped(source):
    block=text_block(source,pilot.circuit.TOP)
    if pilot.circuit.SHIFT+'_taper_16_32_64' not in block:raise ValueError('Use the completed first real taper')
    for name,node in [('XCOUTP','OUTP'),('XCOUTN','OUTN')]:
        old=f'{name} {node} VSS sky130_fd_pr__cap_mim_m3_1 w=10 l=10'
        if block.splitlines().count(old)!=1:raise ValueError('Original symmetric output MIM changed')
        block=block.replace(old,old.replace('w=10 l=10','w=30 l=30'))
    return replace(source,pilot.circuit.TOP,block)


def stimulus_polarity(deck,positive):
    rows=re.findall(r'(?m)^VD D 0 PWL\(([^\n]+)\)',deck)
    if len(rows)!=1:raise ValueError('Expected one original logic stimulus')
    fields=rows[0].split()
    if len(fields)%2 or float(fields[1])!=0 or any(float(v) not in [0,1.8] for v in fields[1::2]):raise ValueError('Unexpected logic levels')
    if not positive:return deck
    changed=' '.join(f'{at} {1.8-float(value):.12g}' for at,value in zip(fields[::2],fields[1::2]))
    return deck.replace('VD D 0 PWL('+rows[0]+')','VD D 0 PWL('+changed+')')


def initial_dc(w,h):
    keep=(w[:,1]>=0)&(w[:,1]<=8e-9);p=w[keep,h['V(P)']];n=w[keep,h['V(N)']]
    if len(p)<2:raise ValueError('Missing solved initial DC interval')
    return dict(differential_v=float(np.mean(p-n)),common_mode_v=float(np.mean((p+n)/2)),
        differential_pp_v=float(np.ptp(p-n)),common_mode_pp_v=float(np.ptp((p+n)/2)))


def transitions(w,h,low,high):
    if not low<0<high:raise ValueError('Fresh two-polarity DC calibration failed')
    t=w[:,1];d=w[:,h['V(P)']]-w[:,h['V(N)']];rows=[]
    for rising in [True,False]:
        a_level=low+(.2 if rising else .8)*(high-low);b_level=low+(.8 if rising else .2)*(high-low)
        aa=edges(t,d,level=a_level,rising=rising);bb=edges(t,d,level=b_level,rising=rising)
        for a in aa[(aa>=20e-9)&(aa<=75e-9)]:
            after=bb[bb>a]
            if not len(after) or after[0]>75e-9:continue
            b=after[0]
            if b-a>=1.25e-9:raise ValueError('Missing paired differential transition')
            values=np.r_[a_level,d[(t>a)&(t<b)],b_level]
            rows.append(dict(rising=rising,duration_ps=float((b-a)*1e12),monotonic=bool(np.all(np.diff(values)*(1 if rising else -1)>=-1e-6))))
    if len(rows)<40 or {r['rising'] for r in rows}!={True,False}:raise ValueError('Insufficient calibrated output transitions')
    durations=[r['duration_ps'] for r in rows];monotonic=all(r['monotonic'] for r in rows)
    return dict(edges=len(rows),min_ps=min(durations),max_ps=max(durations),monotonic=monotonic,
        reference_limits_ps=[260,375],within_reference=bool(monotonic and min(durations)>=260 and max(durations)<=375))


def prepare(parent):
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/driver_gate_taper'):raise ValueError('Use completed first source taper in pinned ngspice')
    m=json.loads((parent/'manifest.json').read_text());i=m['identity'];name='taper_16_32_64';folder=parent/name;task=next(t for t in m['tasks'] if t['id']==name)
    if parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Source taper context changed')
    r=json.loads((folder/'summary.json').read_text())
    if r.get('returncode')!=0 or r.get('manifest_sha256')!=sha(parent/'manifest.json'):raise ValueError('Require a completed real-MOS pilot')
    if any(sha(folder/n)!=h for n,h in dict(task['files'],**r['files']).items()) or pilot.measure(folder,name)!=r['metrics']:raise ValueError('Completed pilot evidence changed')
    if r['metrics']['rising_output_edges']!=22:raise ValueError('Original pilot lost periodic transitions')
    paths=[parent/'manifest.json']+[folder/n for n in set(task['files'])|set(r['files'])|{'summary.json'}]
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={**i['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},
        code={**i['code'],'probe_driver_output_shape.py':sha(Path(__file__))},simulator=provenance(),
        scope='One calculated output-shaping candidate: first real taper, both existing MIMs changed 10x10 to 30x30 um, all other circuit statements unchanged. Same TT25 80 ns/1 ps fixture and fixed rails/load. Complementary initial logic states provide fresh negative/positive DC calibration. Real gate loading, supply current and added-MOS voltages retained. Source pilot reference comparisons only; no generator compliance, PVT, physical selection or PHY admission.')
    out=ROOT/'build/diagnostics/driver_output_shape'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True);tasks=[];source=shaped((folder/'source.spice').read_text())
    for case in CASES:
        dest=out/case;dest.mkdir(exist_ok=True);deck=(folder/'bench.cir').read_text();include=f'.include "{folder}/source.spice"'
        if deck.count(include)!=1:raise ValueError('Unexpected pilot source inclusion')
        deck=stimulus_polarity(deck.replace(include,f'.include "{dest}/source.spice"'),case=='positive_op')
        ProbeNetwork(source).validate(deck,re.findall(r'V\(([^)]+)\)',re.search(r'(?im)^\.print tran[^\n]+',deck)[0]))
        for n,text in [('source.spice',source),('bench.cir',deck)]:
            p=dest/n
            if p.exists() and p.read_text()!=text:raise ValueError('Prepared output-shaping fixture changed')
            if not p.exists():p.write_text(text)
        tasks.append(dict(id=case,files={n:sha(dest/n) for n in ['source.spice','bench.cir']}))
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/driver_output_shape'):raise ValueError('Use prepared output-shaping pilot')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items())):raise ValueError('Output-shaping context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if [t['id'] for t in m['tasks']]!=CASES or (out/'state.json').exists():raise ValueError('Incomplete or prior output-shaping campaign')
        results=[]
        for task in m['tasks']:
            folder=out/task['id']
            if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Output-shaping fixture changed')
            if any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log','summary.json']):raise ValueError('Partial output-shaping output retained')
            atomic(out/'state.json',dict(status='waiting_'+task['id'],qualified_phy=False))
            with lease(ROOT,priority=2,label='driver_shape_'+task['id']):
                unchanged();atomic(out/'state.json',dict(status='running_'+task['id'],qualified_phy=False))
                p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(p.stdout+p.stderr);unchanged();metrics=None;dc=None
            if p.returncode==0:metrics=pilot.measure(folder,'taper_16_32_64');dc=initial_dc(*read_wave(folder/'bench.cir.prn'))
            result=dict(task=task['id'],returncode=p.returncode,metrics=metrics,initial_dc=dc,qualified_phy=False,manifest_sha256=stamp,
                files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',result);results.append(result)
            if metrics is None:break
        complete=len(results)==2 and all(r['metrics'] is not None for r in results);waveforms={};passed=False
        if complete:
            low,high=[r['initial_dc']['differential_v'] for r in results]
            if low<0<high:
                waveforms={case:transitions(*read_wave(out/case/'bench.cir.prn'),low,high) for case in CASES}
                dc_ok=all(.25<=abs(r['initial_dc']['differential_v'])<=.45 and 1.125<=r['initial_dc']['common_mode_v']<=1.375 and max(r['initial_dc'][n] for n in ['differential_pp_v','common_mode_pp_v'])<=1e-4 for r in results)
                passed=bool(dc_ok and all(v['within_reference'] for v in waveforms.values()) and all(r['metrics']['common_mode_pp_v']<=.150 and r['metrics']['rising_output_edges']==22 for r in results))
        capture_manifest(out/'summary.json',dict(results=results,diagnostic_complete=complete,calibrated_transitions=waveforms,source_pilot_reference_checks_passed=passed,manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_diagnostic' if complete else 'held_numerical_failure',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
