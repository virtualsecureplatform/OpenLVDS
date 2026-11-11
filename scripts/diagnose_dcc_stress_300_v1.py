#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Locate native terminal-stress peaks in complete DCC case traces."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from native_binary_raw_v2 import validate
from xyce_profile_300 import ROOT,sha
from qualify_dcc_xyce_300_v1 import save


def analyze(artifact,cases):
    inputs={str(Path(__file__).resolve()):sha(__file__)}
    rows=[]
    for case in cases:
        folder=artifact/case
        receipt=folder/'summary.json'
        r=json.loads(receipt.read_text())
        if r.get('complete') is not True or r.get('error') is not None:
            raise ValueError('Require a complete successful native case: '+case)
        task=r['task'].get('parent_task',r['task'])
        for n in ['bench.raw','bench.cir']:
            if sha(folder/n)!=r['files'][n]:
                raise ValueError('Captured case changed: '+n)
            inputs[str(folder/n)]=sha(folder/n)
        inputs[str(receipt)]=sha(receipt)
        names,w=validate(folder/'bench.raw',set(),task['stop'])
        index={n:k for k,n in enumerate(names)}
        t=w[:,index['time']]
        def get(n):
            return np.zeros(len(w)) if n=='0' else w[:,index['v('+n.lower().replace(':','.')+')']]
        devices=[]
        for device in task['observations']['devices']:
            d,g,s,b=[get(n) for n in device['terminals']]
            pairs={'gs':g-s,'gd':g-d,'gb':g-b,'ds':d-s,'db':d-b,'sb':s-b}
            details={}
            for name,values in pairs.items():
                magnitude=np.abs(values);k=int(np.argmax(magnitude));limit=device['limit_v']
                # Linear interpolation of |V| samples estimates excess duration.
                left,right=magnitude[:-1],magnitude[1:]
                fraction=np.where((left>limit)&(right>limit),1.,0.)
                crossing=(left>limit)!=(right>limit)
                fraction[crossing]=(np.maximum(left[crossing],right[crossing])-limit)/np.abs(right[crossing]-left[crossing])
                details[name]=dict(maximum_abs_v=float(magnitude[k]),signed_peak_v=float(values[k]),peak_time_ns=float(t[k]*1e9),
                                   excess_duration_ps=float(np.sum(fraction*np.diff(t))*1e12))
            worst=max(details,key=lambda n:details[n]['maximum_abs_v'])
            if details[worst]['maximum_abs_v']>device['limit_v']:
                devices.append(dict(device=device['name'],model=device['model'],terminals=device['terminals'],
                                    limit_v=device['limit_v'],worst_pair=worst,pairs=details))
        devices.sort(key=lambda d:d['pairs'][d['worst_pair']]['maximum_abs_v'],reverse=True)
        rows.append(dict(case=case,variant=task['variant'],spec=task['spec'],over_limit_devices=len(devices),devices=devices))
    identity=dict(version='dcc-stress-diagnosis-300-v1',inputs=inputs,cases=cases,artifact=str(artifact.relative_to(ROOT)))
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/reports/dcc_stress_300_v1'/key
    out.mkdir(parents=True,exist_ok=False)
    save(out/'summary.json',dict(identity=identity,rows=rows,qualified_phy=False,
                                scope='Complete native sampled terminal-stress diagnosis; no reliability waiver or physical qualification'))
    print(out,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('cases',nargs='+');a=p.parse_args()
    analyze(a.artifact.resolve(),a.cases)
