#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Locate measured terminal-pair stress peaks in completed native counter traces."""
import argparse
import itertools
import json
from pathlib import Path
import sys
import numpy as np
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha

ROOT=Path(__file__).resolve().parents[1]


def diagnose(folder):
    manifest=folder.parent/'manifest.json';summary=folder/'summary.json'
    m=json.loads(manifest.read_text());r=json.loads(summary.read_text());task=r['task']
    if task not in m['tasks'] or task['id']!=folder.name or r['error'] is not None or r['result'] is None:
        raise ValueError('Require a completed native case from its captured task manifest')
    inputs={str(p.relative_to(ROOT)):sha(p) for p in [manifest,summary,*[folder/n for n in r['files']]]}
    if any(sha(folder/n)!=h for n,h in r['files'].items()):raise ValueError('Completed case bytes changed')
    devices=m['identity']['devices'];lookup={d['name']:d for d in devices}
    failed=[d for d in r['result']['terminal_stress'] if not d['passed']]
    requested={'v('+n.replace(':','.').lower()+')' for d in failed for n in lookup[d['device']]['terminals'] if n!='0'}
    names,w=validate(folder/'bench.raw',requested,26e-9);idx={n:i for i,n in enumerate(names)}
    zero=np.zeros(len(w));t=w[:,idx['time']];rows=[]
    def get(node):return zero if node=='0' else w[:,idx['v('+node.replace(':','.').lower()+')']]
    for stored in failed:
        d=lookup[stored['device']];nodes=d['terminals'];values=[get(n) for n in nodes];worst=None
        for a,b in itertools.combinations(range(4),2):
            differences=np.abs(values[a]-values[b]);sample=int(np.argmax(differences));peak=float(differences[sample])
            if worst is None or peak>worst[0]:worst=(peak,sample,a,b)
        peak,sample,a,b=worst
        if abs(peak-stored['max_terminal_difference_v'])>1e-12:raise ValueError('Stored terminal stress does not reproduce')
        observed={label:dict(node=node,voltage_v=float(values[k][sample])) for k,(label,node) in enumerate(zip(('drain','gate','source','body'),nodes))}
        context={n:float(w[sample,idx[n]]) for n in ('v(clk)','v(request)','v(xd.xr.low0_sn)','v(xd.xr.low0)') if n in idx}
        rows.append(dict(device=d['name'],model=d['model'],time_ps=float(t[sample]*1e12),peak_v=peak,limit_v=stored['limit_v'],
                         worst_pair=[('drain','gate','source','body')[k] for k in (a,b)],terminals=observed,context=context))
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Case changed during read-only diagnosis')
    return dict(case=str(folder.relative_to(ROOT)),task=task,inputs=inputs,code_sha256=sha(Path(__file__)),
                failed_devices=rows,stored_terminal_peaks_reproduced=True,
                scope='Read-only exact-sample native terminal diagnosis; no circuit change or timing/PHY admission',qualified_phy=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('case',type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();result=diagnose(a.case.resolve());out=a.output.resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(out)
