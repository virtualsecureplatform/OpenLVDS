#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read only an aborted combined trace prefix; never a qualification reader."""
import argparse
import json
from pathlib import Path
import re
import numpy as np
import probe_dcc_chain_300_v1 as producer


def read_prefix(raw):
    marker=raw.index(b'Binary:\n')+8;header=raw[:marker].decode()
    variables=int(re.search(r'No\. Variables:\s*(\d+)',header)[1])
    declared=int(re.search(r'No\. Points:\s*(\d+)',header)[1])
    lines=header.split('Variables:\n',1)[1].split('Binary:',1)[0].splitlines()
    names=[line.split()[1] for line in lines if line.strip()]
    if declared!=0 or variables<=0 or len(names)!=variables or len(set(names))!=variables or names[0]!='time':
        raise ValueError('Require the explicitly aborted zero-point header and complete variable list')
    rows,trailing=divmod(len(raw)-marker,variables*8)
    if not rows or trailing:raise ValueError('Refuse incomplete binary records; never trim failed witnesses')
    wave=np.frombuffer(raw[marker:],dtype='<f8').reshape(rows,variables)
    if not np.isfinite(wave).all() or wave[0,0]!=0 or np.any(np.diff(wave[:,0])<=0):
        raise ValueError('Invalid failed-prefix samples')
    return names,wave


def inspect(folder):
    parent=folder.parent;manifest=producer.bound(parent,full=False)
    row=json.loads((folder/'summary.json').read_text())
    task=next(t for t in manifest['tasks'] if t['id']==folder.name)
    if row['task']!=task or row['error'] is None or row['result'] is not None:
        raise ValueError('Require an original terminal numerical failure without a measurement result')
    for n in ('bench.raw','observations.json','ngspice.log'):
        if producer.sha(folder/n)!=row['files'][n]:raise ValueError('Failed native witness changed')
    names,w=read_prefix((folder/'bench.raw').read_bytes());index={n:k for k,n in enumerate(names)}
    if w[-1,0]>=2.1e-9:raise ValueError('This diagnostic is limited to the failed pre-clock startup prefix')
    obs=json.loads((folder/'observations.json').read_text());maps=list(obs['sections'].values())+list(obs['dcc'].values())
    get=lambda n:np.zeros(len(w)) if n=='0' else w[:,index['v('+n.replace(':','.').lower()+')']]
    stress=[]
    for o in maps:
        for d in o['devices']:
            voltage=[get(n) for n in d['terminals']];span=np.maximum.reduce(voltage)-np.minimum.reduce(voltage)
            stress.append(dict(device=d['name'],dc_span_v=float(span[0]),prefix_peak_v=float(span.max()),limit_v=d['limit_v']))
    return dict(stored_rows=len(w),last_prefix_time_s=float(w[-1,0]),native_mos=len(stress),
        maximum_dc_span_v=max(r['dc_span_v'] for r in stress),
        prefix_stress_violations=sum(r['prefix_peak_v']>r['limit_v'] for r in stress),
        worst=sorted(stress,key=lambda r:r['prefix_peak_v'],reverse=True)[:3],
        dc_nodes_v={n:float(get(n)[0]) for n in ('VDD','IN','DCC_RESET_N','DCC0_OUT','DCC1_OUT')},
        failed_point_preserved=True,complete_qualification_trace=False,qualified_phy=False,
        scope='Aborted zero-point-header startup prefix only; no full voltage/stress, functional or PHY qualification')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    args=parser.parse_args();print(json.dumps(inspect(args.folder.resolve()),indent=2))
