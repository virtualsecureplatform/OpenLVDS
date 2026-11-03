#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Add real internal observations to one completed failing native TT25 pilot."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np

import assemble_driver_compact_native as assembly
import driver_native_stress as stress
import probe_driver_compact_native as pilot
from dll_campaign import atomic,text_block
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command,provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
sha=assembly.sha
CASE='tt_25_negative_op'


def fixture(deck,old,new,model,observations):
    include=f'.include "{old}/source.spice"'
    if (deck.count(include)!=1 or re.findall(r'(?im)^\.tran[^\n]+',deck)!=['.tran 1p 80n 0 1p'] or
            re.findall(r'(?im)^\.print tran[^\n]+',deck)!=['.print tran V(D) V(P) V(N)']):
        raise ValueError('Require the complete public-only native pilot fixture')
    probes={n:'XD:XCORE:'+v['native_node'] for n,v in observations.items()}
    probes.update(NB='XD:NB',VDDIO='VDDIO',VDDD='VDDD',VREF='VREF',PB='IREF')
    rows=stress.terminal_observations(model,deck)
    if len(rows)!=305 or sum(r['device'].startswith('XD:XCORE:') for r in rows)!=302:
        raise ValueError('Require unchanged native core and original three-MOS source bias')
    added=stress.voltage_probes(rows)
    result=deck.replace(include,f'.include "{new}/source.spice"').replace(
        '.print tran V(D) V(P) V(N)', '.print tran V(D) V(P) V(N) '+' '.join('V('+v+')' for v in probes.values()))
    if result.splitlines().count('.end')!=1: raise ValueError('Unexpected observer terminator')
    result=result.replace('.end','.save '+' '.join('V('+v+')' for v in added)+'\n.end')
    ProbeNetwork(model).validate(result,['D','P','N',*probes.values(),*added])
    return result,probes,rows


def prepare(parent,assembled):
    m=pilot.bound(parent);old=parent/CASE
    task=next(t for t in m['tasks'] if t['id']==CASE)
    r=json.loads((old/'summary.json').read_text())
    if (r['returncode']!=0 or r['error'] is not None or r['manifest_sha256']!=sha(parent/'manifest.json') or
            any(sha(old/n)!=h for n,h in r['files'].items()) or
            pilot.measure(old)!=(r['metrics'],r['initial_dc']) or r['metrics']['common_mode_pp_v']<=.150):
        raise ValueError('Require the completed, unchanged TT25 common-mode failure')
    a=json.loads((assembled/'summary.json').read_text())
    if assembly.assemble(ROOT/a['identity']['extraction'])!=assembled or a['identity']['extraction']!=m['identity']['extraction']:
        raise ValueError('Observer and pilot physical driver differ')
    model=(old/'source.spice').read_text()
    if text_block(model,assembly.TOP)!=text_block((assembled/'native.spice').read_text(),assembly.TOP):
        raise ValueError('Observer changed the actual native core')
    # The native pilot's source bias is deliberately retained: observations
    # must reproduce the failure before any bias or compensation experiment.
    core=text_block(model,assembly.TOP)
    ext=(assembled/'observation_flat.ext').read_text()
    extra=assembly.observations(ext,core,dict(CM=dict(physical_pin='I26.R2'),CMS=dict(physical_pin='I28.R2')))
    observations=dict(a['observations'],**extra)
    inputs=dict(m['identity']['inputs'],**a['identity']['inputs'])
    inputs.update({str((assembled/n).relative_to(ROOT)):h for n,h in a['files'].items()})
    inputs.update({str((old/n).relative_to(ROOT)):h for n,h in dict(task['files'],**r['files']).items()})
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in [old/'summary.json',parent/'manifest.json',assembled/'summary.json']})
    code=dict(m['identity']['code'],**a['identity']['code'])
    code.update({n:sha(ROOT/'scripts'/n) for n in ['observe_compact_driver_loop.py','driver_native_stress.py','assemble_driver_compact_native.py']})
    identity=dict(parent=str(parent.relative_to(ROOT)),case=CASE,assembly=str(assembled.relative_to(ROOT)),
        inputs=inputs,code=code,simulator=provenance(),observations=observations,
        scope='Observation-only repeat of the completed failing native TT25 negative pilot. '
              'Byte-identical core and original source bias, unchanged 80 ns/1 ps '
              'fixture, rails, reference, load and all R/C/MOS devices. Actual '
              'internal conductor labels and all MOS terminal voltages added. '
              'Require exact public-waveform reproduction. No compensation '
              'change, numerical repair, electrical admission or PHY qualification.')
    out=ROOT/'build/diagnostics/driver_compact_loop_observation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    deck,probes,rows=fixture((old/'bench.cir').read_text(),old,out,model,observations)
    files={}
    for name,text in [('source.spice',model),('bench.cir',deck),('probes.json',json.dumps(probes,sort_keys=True,indent=2)+'\n'),
                      ('mos_observations.json',json.dumps(rows,sort_keys=True,indent=2)+'\n')]:
        path=out/name
        if path.exists() and path.read_text()!=text: raise ValueError('Prepared observer changed')
        if not path.exists():path.write_text(text)
        files[name]=sha(path)
    capture_manifest(out/'manifest.json',dict(identity=identity,files=files,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/driver_compact_loop_observation') or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
            any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
            any(sha(out/n)!=h for n,h in m['files'].items())):
        raise ValueError('Observation-only native context changed')
    return m


def measure(out,m):
    metrics,dc=pilot.measure(out)
    w,h=read_wave(out/'bench.cir.prn');base,_=read_wave(ROOT/m['identity']['parent']/CASE/'bench.cir.prn')
    matches=bool(np.array_equal(w[:,:5],base[:,:5]))
    probes=json.loads((out/'probes.json').read_text());t=w[:,1];windows=[]
    for start,end in [(0,8),(20,30),(30,40),(40,50),(50,60),(60,70),(70,75)]:
        keep=(t>=start*1e-9)&(t<=end*1e-9)
        values={n:w[keep,h['V('+v+')']] for n,v in probes.items()}
        values['output_common_mode']=(w[keep,h['V(P)']]+w[keep,h['V(N)']])/2
        windows.append(dict(start_ns=start,end_ns=end,nodes={n:dict(mean_v=float(v.mean()),min_v=float(v.min()),max_v=float(v.max())) for n,v in values.items()}))
    names,raw=read_raw(out/'bench.raw')
    sampled=stress.measure(names,raw,json.loads((out/'mos_observations.json').read_text()))
    return dict(public_waveform_matches_original=matches,metrics=metrics,initial_dc=dc,windows=windows,
                sampled_mos_voltages=sampled)


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if any((out/n).exists() for n in ['state.json','bench.raw','ngspice.log','summary.json']):
            raise ValueError('Prior or partial native observation retained')
        atomic(out/'state.json',dict(status='waiting_for_slot',qualified_phy=False))
        with lease(ROOT,priority=2,label='compact_driver_loop_observer'):
            bound(out);atomic(out/'state.json',dict(status='running',qualified_phy=False))
            result=subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(result.stdout+result.stderr);bound(out)
        measured=None;error=None
        try:
            result.check_returncode();measured=measure(out,m)
            if measured['public_waveform_matches_original'] is not True: raise ValueError('Observation-only repeat changed public waveform')
        except Exception as caught:error=str(caught)
        capture_manifest(out/'summary.json',dict(returncode=result.returncode,error=error,observation_complete=error is None,
            measurements=measured,manifest_sha256=stamp,qualified_phy=False,scope=m['identity']['scope'],
            files={n:sha(out/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (out/n).exists()}))
        atomic(out/'state.json',dict(status='completed_observation' if error is None else 'held_for_diagnosis',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--assembly',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.assembly is None:p.error('--assembly required')
        print(prepare(a.artifact.resolve(),a.assembly.resolve()),flush=True)
    else:run(a.artifact.resolve())
