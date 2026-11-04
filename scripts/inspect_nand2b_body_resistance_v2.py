#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare positive-resistor body-to-rail path bounds in two verified RC families.

A shortest series path is an upper bound on passive effective resistance;
parallel paths, intrinsic junctions and transient capacitance are not replaced
by this diagnostic. No circuit element or simulation model is changed.
"""
import argparse
import hashlib
import heapq
import json
import math
from pathlib import Path
import native_clock_components_v2 as parsing
from audit_passive_rc_v3 import audit
from reduce_rc import number
from spice_library import checked_netlist
from probe_digital_dcc_v2 import sha,atomic

ROOT=Path(__file__).resolve().parents[1]
VERSION='native-nand2b-body-positive-r-path-upper-bounds-v2.1'


def paths(text):
    definitions=parsing.definitions(text)
    if len(definitions)!=1:raise ValueError('Require one flat native RC model')
    _,body=next(iter(definitions.values()));graph={};devices=[]
    for raw in body:
        w=' '.join(raw).split('$',1)[0].split()
        if not w:continue
        if w[0][0].upper()=='R':
            if len(w)!=4:raise ValueError('Require a four-field native resistor')
            value=number(w[3])
            if not math.isfinite(value) or value<=0:raise ValueError('Require positive finite resistor')
            for a,b in [(w[1],w[2]),(w[2],w[1])]:graph.setdefault(a,[]).append((b,value))
        elif w[0][0].upper()=='X':
            end=next((i for i,v in enumerate(w) if '=' in v),len(w));model=w[end-1]
            if 'nfet_' in model or 'pfet_' in model:
                if end!=6:raise ValueError('Wrong native MOS interface')
                devices.append(dict(device=w[0],model=model,body=w[4],rail='VGND' if 'nfet_' in model else 'VPWR'))
    distances={}
    for rail in ['VGND','VPWR']:
        dist={rail:0.};queue=[(0.,rail)]
        while queue:
            d,a=heapq.heappop(queue)
            if d!=dist[a]:continue
            for b,r in graph.get(a,[]):
                new=d+r
                if new<dist.get(b,math.inf):dist[b]=new;heapq.heappush(queue,(new,b))
        distances[rail]=dist
    if not devices:raise ValueError('Missing native MOS body witnesses')
    for d in devices:
        if d['body'] not in distances[d['rail']]:raise ValueError('Native body is not connected to its supply rail')
        d['shortest_r_path_upper_bound_ohm']=distances[d['rail']][d['body']]
    return dict(devices=devices,maximum_by_rail_ohm={r:max((d['shortest_r_path_upper_bound_ohm'] for d in devices if d['rail']==r),default=None) for r in distances})


def compare(baseline,bodytap):
    rows=[];files=[]
    for parent,version in [(baseline,'independent-native-nand2b-shunts-passive-rc-verification-v2.1'),
                           (bodytap,'independent-native-nand2b-bodytap-passive-rc-verification-v2.1')]:
        m=json.loads((parent/'manifest.json').read_text());i=m['identity'];s=json.loads((parent/'summary.json').read_text())
        if (i['version']!=version or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or not s['passed'] or len(s['rows'])!=2 or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())):
            raise ValueError('Require complete unchanged independent native RC receipts')
        reports=[];files += [parent/'manifest.json',parent/'summary.json']+[ROOT/n for n in {**i['inputs'],**i['code']}]
        for row in s['rows']:
            info=row['extraction'];text=checked_netlist(info)
            if not row['rc_topology_passed'] or not audit(text)['elementwise_passive_passed']:raise ValueError('Require passive verified body network')
            reports.append(dict(macro=row['macro'],**paths(text)));files += [ROOT/info['netlist'],ROOT/info['raw_netlist']]
        rows.append(dict(parent=str(parent.relative_to(ROOT)),models=reports))
    code=[Path(__file__),Path(parsing.__file__),ROOT/'scripts/audit_passive_rc_v3.py',ROOT/'scripts/reduce_rc.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,baseline=str(baseline.relative_to(ROOT)),bodytap=str(bodytap.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files+code})
    out=ROOT/'build/diagnostics/nand2b_body_resistance_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'summary.json',dict(identity=identity,rows=rows,qualified_phy=False,
        scope='Unmodified passive shortest-series-path resistance upper bounds only; no effective-resistance, transient, new reduced-model or timing admission'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('baseline',type=Path);p.add_argument('bodytap',type=Path);a=p.parse_args()
    print(compare(a.baseline.resolve(),a.bodytap.resolve()),flush=True)
