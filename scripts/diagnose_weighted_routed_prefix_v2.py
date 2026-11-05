#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reproduce negative terminal observations in an exact bounded routed raw prefix.

Append-only growth is allowed. A semantic header and exact complete-record
payload are bound; live metadata and partial tail bytes cannot admit a trace.
No solver lock, queue ticket, producer, raw data or acceptance gate is changed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import numpy as np
import probe_weighted_routed_v2 as pilot
import run_native_binary_v2 as runner

ROOT=pilot.ROOT
VERSION='bounded-routed-native-terminal-prefix-diagnosis-v2.1'
CONTEXT='weighted_routed_prefix_diagnosis_v2'
ROLES=['drain','gate','source','body']


def payload_sha(path,offset,size):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        stream.seek(offset)
        while size:
            chunk=stream.read(min(size,1024*1024))
            if not chunk:raise ValueError('Raw prefix was truncated during observation')
            digest.update(chunk);size-=len(chunk)
    return digest.hexdigest()


def prefix(path,records):
    if sys.byteorder!='little' or not isinstance(records,int) or isinstance(records,bool) or records<2:
        raise ValueError('Require at least two complete little-endian native records')
    with path.open('rb') as stream:
        header=b''
        while True:
            line=stream.readline(1024*1024);header+=line
            if not line or len(header)>1024*1024:raise ValueError('Missing bounded native binary header')
            if line==b'Binary:\n':break
        offset=stream.tell()
    text=header.decode();counts=re.findall(r'^No\. Variables:\s*(\d+)\s*$',text,re.M)
    if (text.count('Flags: real\n')!=1 or text.count('Plotname: Transient Analysis\n')!=1 or len(counts)!=1):
        raise ValueError('Require real native transient prefix')
    entries=re.findall(r'^\s*(\d+)\s+(\S+)\s+(\S+)\s*$',text,re.M)
    names=[m[1].lower() for m in entries];titles=re.findall(r'^Title: (.+)$',text,re.M)
    n=int(counts[0]);size=records*n*8
    if len(titles)!=1 or [int(m[0]) for m in entries]!=list(range(n)) or n<2 or len(names)!=n or len(set(names))!=n or 'time' not in names or path.stat().st_size<offset+size:
        raise ValueError('Incomplete records or ambiguous/missing native vectors')
    before=payload_sha(path,offset,size)
    w=np.memmap(path,dtype='<f8',mode='r',offset=offset,shape=(records,n))
    previous=None;ti=names.index('time')
    for start in range(0,records,128):
        block=w[start:start+128];t=block[:,ti]
        if (not np.isfinite(block).all() or t[0]<0 or (previous is not None and t[0]<=previous) or np.any(np.diff(t)<=0)):
            raise ValueError('Nonfinite or nonmonotonic raw prefix')
        previous=float(t[-1])
    semantic=dict(title=titles[0].lower(),flags='real',plot='Transient Analysis',vectors=names)
    binding=dict(title=titles[0].lower(),complete_records=records,variables=n,payload_bytes=size,payload_sha256=before,
        semantic_header_sha256=hashlib.sha256(json.dumps(semantic,sort_keys=True).encode()).hexdigest(),
        first_time_s=float(w[0,ti]),last_time_s=float(w[-1,ti]),byteorder='little')
    if payload_sha(path,offset,size)!=before:raise ValueError('Consumed raw prefix changed while observing')
    return names,w,binding,offset


def terminal_observations(names,w,devices):
    idx={n:i for i,n in enumerate(names)};n=len(names)
    if not devices or len({d['name'] for d in devices})!=len(devices):raise ValueError('Missing/duplicate native device witness')
    def column(node):
        if node=='0':return n
        key='v('+node.replace(':','.').lower()+')'
        if key not in idx:raise ValueError('Missing native terminal vector '+key)
        return idx[key]
    if any(len(d['terminals'])!=4 or d['limit_v']!=1.95 for d in devices):
        raise ValueError('Native four-terminal coverage or original 1.95 V limit changed')
    columns=np.array([[column(p) for p in d['terminals']] for d in devices]);peaks=np.full(len(devices),-1.)
    where=np.zeros(len(devices),dtype=int)
    for start in range(0,len(w),128):
        values=np.take(w[start:start+128],np.minimum(columns,n-1),axis=1);values[:,columns==n]=0
        span=np.ptp(values,axis=2);local=np.argmax(span,axis=0);maximum=span[local,np.arange(len(devices))]
        update=maximum>peaks;peaks[update]=maximum[update];where[update]=start+local[update]
    rows=[];ti=idx['time']
    for number in np.flatnonzero(peaks>1.95):
        d=devices[number];k=int(where[number]);cols=columns[number]
        values=np.array([0. if c==n else w[k,c] for c in cols]);hi=int(np.argmax(values));lo=int(np.argmin(values))
        rows.append(dict(device=d,peak_record=k,peak_v=float(peaks[number]),peak_time_ps=float(w[k,ti]*1e12),
            highest_terminal=d['terminals'][hi],lowest_terminal=d['terminals'][lo],
            highest_role=ROLES[hi],lowest_role=ROLES[lo],terminal_values_v=list(map(float,values))))
    rows.sort(key=lambda r:(-r['peak_v'],r['device']['name']));worst=int(np.argmax(peaks))
    return dict(screened_native_mos=len(devices),six_terminal_pairs_per_device=True,
        maximum_observed_terminal_difference_v=float(peaks[worst]),worst_observed_device=devices[worst]['name'],
        violating_devices=len(rows),violating_model_counts=dict(sorted(Counter(r['device']['model'] for r in rows).items())),
        highest_terminal_role_counts=dict(sorted(Counter(r['highest_role'] for r in rows).items())),rows=rows)


def pulse_slots(names,w,spec):
    idx={n:i for i,n in enumerate(names)}
    if not {'time','v(in)','v(out)'}<=set(idx):raise ValueError('Missing input/output vectors')
    t=w[:,idx['time']]*1e12;rows=[]
    for slot,code in enumerate(spec['codes']):
        if t[-1]<(slot+1)*10000:break
        mask=(t>=slot*10000)&(t<=(slot+1)*10000);row=dict(slot=slot,code=code)
        for up,label in [(True,'rise'),(False,'fall')]:
            a=pilot.crossings(t[mask],w[mask,idx['v(in)']],up);b=pilot.crossings(t[mask],w[mask,idx['v(out)']],up)
            row[label+'_input_edges']=len(a);row[label+'_output_edges']=len(b)
            row[label+'_delay_ps']=float(b[0]-a[0]) if len(a)==len(b)==1 else None
        rows.append(row)
    return rows


def observe(parent,case,records):
    m=pilot.bound(parent);i=m['identity'];task=next((t for t in m['tasks'] if t['id']==case),None)
    if task is None:raise ValueError('Unknown routed pilot task')
    text,witness,components,files=pilot.libraries(ROOT/i['receipt'])
    if text!=(parent/'bank.spice').read_text() or witness!=i['witness'] or components!=i['components']:
        raise ValueError('Fresh whole-bank RC or native witnesses cannot be regenerated')
    c=i['components'];gate=json.loads((parent/'control_gate.json').read_text())
    if pilot.control_gate.require(ROOT/gate['receipt'],ROOT/c['clock'],ROOT/c['fine_cells'],ROOT/c['repair'])!=gate:
        raise ValueError('Physical fine-control prerequisite changed')
    folder=parent/case;deck=(folder/'bench.cir').read_text();translated,_=runner.translate(deck)
    if deck!=pilot.fixture(parent,task['spec'],witness) or translated!=(folder/'bench.ngspice.cir').read_text():
        raise ValueError('Prepared or actual solver deck changed')
    path=folder/'bench.raw';names,w,raw,offset=prefix(path,records)
    if raw['last_time_s']>=len(task['spec']['codes'])*10e-9:
        raise ValueError('Use complete-waveform verification for a full-duration trace')
    if raw['title']!=translated.splitlines()[0].lower():raise ValueError('Raw fixture title does not match the actual solver deck')
    stress=terminal_observations(names,w,witness['devices']);slots=pulse_slots(names,w,task['spec'])
    for row in stress['rows']:
        k=row['peak_record']
        row['fine_controls_at_peak_v']=[float(w[k,names.index(f'v(b{bit})')]) for bit in range(5)]
        row['input_at_peak_v']=float(w[k,names.index('v(in)')]);row['output_at_peak_v']=float(w[k,names.index('v(out)')])
    if payload_sha(path,offset,raw['payload_bytes'])!=raw['payload_sha256']:raise ValueError('Consumed prefix changed during measurement')
    files += [parent/n for n in ['manifest.json','bank.spice','control_gate.json']]
    files += [folder/n for n in ['bench.cir','bench.ngspice.cir']]
    files += [Path(__file__),Path(pilot.__file__),Path(runner.__file__),ROOT/'scripts/weighted_routed_observation_v2.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),case=case,task=task,raw=raw,
        inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in files})
    pilot.bound(parent)
    result=dict(identity=identity,terminal_observations=stress,complete_input_slots=slots,
        prefix_finite_monotonic=True,completed_transient=False,complete_waveform_admitted=False,
        electrical_qualification_passed=False,legal_code_table_admitted=False,qualified_phy=False,
        scope='Exact regenerated routed context and bounded real raw records only; negative terminal observations, no complete timing/settling/safety or PHY admission')
    return result


def diagnose(parent,case,records):
    result=observe(parent,case,records);i=result['identity']
    if any(pilot.sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Static context changed during prefix diagnosis')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);pilot.atomic(out/'summary.json',result);return out


def verify(out):
    retained=json.loads((out/'summary.json').read_text());i=retained['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(pilot.sha(ROOT/n)!=h for n,h in i['inputs'].items())):
        raise ValueError('Prefix diagnosis identity or static context changed')
    measured=observe(ROOT/i['parent'],i['case'],i['raw']['complete_records'])
    if measured!=retained:raise ValueError('Bounded prefix payload or native terminal observations changed')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--case',default='0');p.add_argument('--records',type=int);p.add_argument('--verify',action='store_true')
    a=p.parse_args()
    if not a.verify and a.records is None:p.error('Provide --records for a new bounded diagnosis')
    print(verify(a.artifact.resolve()) if a.verify else diagnose(a.artifact.resolve(),a.case,a.records),flush=True)
