#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe preserved raw frames from a terminal abort; never qualification data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def prefix(data):
    marker=b'Binary:\n';position=data.index(marker)+len(marker);header=data[:position].decode()
    n=int(re.search(r'No\. Variables:\s*(\d+)',header)[1]);declared=int(re.search(r'No\. Points:\s*(\d+)',header)[1])
    names=[m[1].lower() for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$',header,re.M)]
    if 'complex' in header or n<1 or len(names)!=n or 'time' not in names:raise ValueError('Require real time-domain raw prefix')
    frames,remainder=divmod(len(data)-position,n*8)
    if frames<2:raise ValueError('Insufficient complete raw frames')
    w=np.frombuffer(data[position:position+frames*n*8],dtype='<f8').reshape(frames,n)
    t=w[:,names.index('time')]
    if not np.isfinite(w).all() or t[0]<0 or t[0]>1e-15 or np.any(np.diff(t)<=0):raise ValueError('Invalid finite monotonic raw prefix')
    return names,w,dict(declared_points=declared,available_complete_frames=frames,trailing_bytes=remainder,
        completed_waveform=False,scope='Abort-prefix observation only; an unfinalized raw header cannot pass the normal waveform reader or qualify a circuit.')


def observe(folder):
    allowed=['tx_convergence_isolation','tx_decap_isolation','endpoint_decap_isolation','tx_sparse_isolation']
    if not any(folder.is_relative_to(ROOT/'build/diagnostics'/n) for n in allowed):raise ValueError('Use terminal numerical isolation result')
    r=json.loads((folder/'summary.json').read_text());failure=r.get('failure') or ''
    if r.get('returncode')!=1 or r.get('numerically_completed') is not False or 'Timestep too small' not in failure:raise ValueError('Require terminal timestep collapse')
    manifest=folder/'manifest.json' if (folder/'manifest.json').exists() else folder.parent/'manifest.json'
    if sha(manifest)!=r['manifest_sha256']:raise ValueError('Terminal result binding changed')
    for n,h in r['files'].items():
        if sha(folder/n)!=h:raise ValueError('Terminal output changed')
    names,w,metadata=prefix((folder/'bench.raw').read_bytes());t=w[:,names.index('time')]
    reported=float(re.search(r'time = ([\deE.+-]+)',failure)[1])
    if not abs(t[-1]-reported)<1e-12:raise ValueError('Prefix does not reach the reported abort')
    signals={}
    for name,j in zip(names,range(len(names))):
        if name=='time':continue
        v=w[:,j];signals[name]=dict(min_v=float(v.min()),max_v=float(v.max()),last_v=float(v[-1]),
            change_last_ps_v=float(v[-1]-np.interp(t[-1]-1e-12,t,v)))
    paths=[manifest,folder/'summary.json',folder/'bench.raw',folder/'bench.cir',folder/'library.spice']
    identity=dict(inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code={n:sha(ROOT/'scripts'/n) for n in ['observe_failure_prefix.py','receiver_static_diagnosis.py']})
    out=folder/'failure_prefix_observation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'summary.json',dict(identity=identity,**metadata,stop_ns=float(t[-1]*1e9),failure=failure,signals=signals,
        electrical_verdict=None,qualified_phy=False))
    return out/'summary.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(observe(a.artifact.resolve()),flush=True)
