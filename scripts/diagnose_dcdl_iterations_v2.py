#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare completed numerical failures without treating partial raw data as a pass."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import probe_dcdl_iterations_v2 as pilot
import run_native_binary_v2 as runner

ROOT=pilot.ROOT
sha=pilot.sha
VERSION='matched-dcdl-iteration-failure-prefix-diagnosis-v2.1'


def failure(log):
    rows=re.findall(r'Timestep too small; time = ([\deE.+-]+), timestep = ([\deE.+-]+): trouble with node "([^"]+)"',log)
    if len(rows)!=1 or 'run simulation(s) aborted' not in log:
        raise ValueError('Require one completed timestep-collapse failure')
    time,step,node=rows[0];elapsed=re.findall(r'Total elapsed time \(seconds\) = ([\d.]+)',log)
    if len(elapsed)!=1:raise ValueError('Missing terminal solver elapsed time')
    values=[float(time),float(step),float(elapsed[0])]
    if not all(math.isfinite(v) and v>0 for v in values):raise ValueError('Invalid numerical-failure metadata')
    return dict(reported_time_s=values[0],reported_timestep_s=values[1],reported_node=node,solver_elapsed_seconds=values[2])


def prefix(path):
    """Hash terminal aborted-run records; deliberately never qualify a trace."""
    with path.open('rb') as stream:
        header=b''
        while True:
            line=stream.readline(1024*1024)
            if not line or len(header)+len(line)>1024*1024:raise ValueError('Missing bounded native binary header')
            header+=line
            if line==b'Binary:\n':break
        if b'Flags: real\n' not in header or b'Plotname: Transient Analysis\n' not in header:
            raise ValueError('Require real native transient records')
        counts=re.findall(rb'No\. Variables:\s*(\d+)',header)
        if len(counts)!=1 or int(counts[0])<2:raise ValueError('Invalid native variable count')
        count=int(counts[0]);start=stream.tell();size=path.stat().st_size-start
        records,remainder=divmod(size,count*8)
        if remainder or records<2:raise ValueError('Incomplete binary record or missing prefix')
        digest=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        stream.seek(start);first=struct.unpack('=d',stream.read(8))[0]
        stream.seek(start+(records-1)*count*8);last=struct.unpack('=d',stream.read(8))[0]
    if not math.isfinite(first) or not math.isfinite(last) or not 0<=first<last:
        raise ValueError('Invalid partial-transient time endpoints')
    return dict(variables=count,complete_records=records,payload_sha256=digest.hexdigest(),first_time_s=first,last_time_s=last,
                completed_transient=False,qualified_phy=False)


def diagnose(parent,case='2'):
    m,pm=pilot.bound(parent);baseline=ROOT/m['identity']['parent'];rows=[];paths=[]
    task=next(t for t in m['tasks'] if t['id']==case);original=pm['tasks'][int(case)]
    before=(baseline/case/'bench.cir').read_text();after=(parent/case/'bench.cir').read_text()
    if after!=pilot.fixture(before):raise ValueError('Matched decks differ beyond title and ITL4')
    for folder,expected in [(baseline/case,original),(parent/case,task)]:
        row=json.loads((folder/'summary.json').read_text())
        if row['task']!=expected or row['error'] is None or row['result'] is not None:
            raise ValueError('Require two terminal numerical failures at the same case')
        if not {'bench.raw','bench.cir','bench.ngspice.cir','ngspice.log','console.log'}<=set(row['files']):
            raise ValueError('Missing failed-run evidence')
        for name,digest in row['files'].items():
            path=folder/name
            if sha(path)!=digest:raise ValueError('Changed failed-run witness')
            paths.append(path)
        translated,_=runner.translate((folder/'bench.cir').read_text())
        if translated!=(folder/'bench.ngspice.cir').read_text():raise ValueError('Translated solver deck changed')
        log=failure((folder/'ngspice.log').read_text());raw=prefix(folder/'bench.raw')
        if abs(raw['last_time_s']-log['reported_time_s'])>1e-15 or raw['last_time_s']>=2.1e-9:
            raise ValueError('Require the retained pre-input timestep collapse')
        rows.append(dict(folder=str(folder.relative_to(ROOT)),failure=log,prefix=raw));paths.append(folder/'summary.json')
    paths += [parent/'manifest.json',baseline/'manifest.json',Path(__file__),Path(pilot.__file__),Path(runner.__file__)]
    paths += [ROOT/n for n in m['identity']['inputs']]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),case=case,byteorder=sys.byteorder,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})
    out=ROOT/'build/diagnostics/dcdl_iteration_failure_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    a,b=rows
    same_payload=all(a['prefix'][key]==b['prefix'][key] for key in ['variables','complete_records','payload_sha256'])
    same_error=all(a['failure'][key]==b['failure'][key] for key in ['reported_time_s','reported_timestep_s','reported_node'])
    result=dict(identity=identity,rows=rows,only_title_and_itl4_changed=True,translated_decks_verified=True,
                partial_payloads_bit_identical=same_payload,reported_failure_identical=same_error,
                iteration_increase_resolved_failure=False,diagnosis_verified=True,qualified_phy=False,
                scope='Two completed numerical failures and their incomplete pre-input prefixes only; no pulse, timing, voltage-safety, runtime-speedup or PHY admission; reported solver node is not a proven root cause')
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Failure evidence changed during diagnosis')
    out.mkdir(parents=True,exist_ok=False);pilot.atomic(out/'summary.json',result);return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--case',choices=['0','2'],default='2');a=p.parse_args()
    print(diagnose(a.artifact.resolve(),a.case),flush=True)
