#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind completed source-FF failures and identify private charge-kick nodes.

Other producer cases may remain live. Only immutable, complete case raw files
are read; no partial prefix, model modification or electrical admission follows.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import numpy as np
import verify_guarded_clock_prepare_v2 as verification
from native_binary_raw_v2 import validate

ROOT=verification.ROOT
sha=verification.sha
VERSION='native-ff-reset-mode-private-guard-targets-v2.1'


def private_node(name):
    m=re.fullmatch(r'XD:XR:r[012]__(.+)',name)
    return m[1] if m else None


def inspect(t,get,devices):
    selected=set();witnesses=[];uncovered=[]
    for d in devices:
        if not re.match(r'XD:XR:Xr[012]__',d['name']):continue
        if d['limit_v']!=1.95:raise ValueError('Unexpected native FF voltage domain')
        values=[get(n) for n in d['terminals']];worst=(0.,None,None)
        for a,b in itertools.combinations(range(4),2):
            delta=np.abs(values[a]-values[b]);j=int(np.argmax(delta));value=float(delta[j])
            if value>worst[0]:worst=(value,(a,b),j)
        peak,pair,j=worst
        if peak<=1.95:continue
        candidates=[]
        for k in pair:
            node=private_node(d['terminals'][k]);value=float(values[k][j])
            if node is not None and (value<-.001 or value>1.801):candidates.append(node)
        row=dict(device=d['name'],model=d['model'],terminal_pair=list(pair),peak_difference_v=peak,
            time_ps=float(t[j]),nodes=[d['terminals'][k] for k in pair],voltages_v=[float(values[k][j]) for k in pair],
            private_guard_candidates=sorted(candidates))
        witnesses.append(row);selected.update(candidates)
        if not candidates:uncovered.append(row)
    return dict(private_nodes=sorted(selected),violations=witnesses,uncovered_violations=uncovered)


def diagnose(parent):
    m=verification.pilot.bound(parent);devices=verification.regenerate(parent,m);paths=[parent/'manifest.json',*[parent/n for n in m['libraries']]];rows=[]
    for n in range(8):
        folder=parent/str(n);r=json.loads((folder/'summary.json').read_text());task=m['tasks'][n];spec=task['spec']
        if (r['task']!=task or r['error'] is not None or r['result']['terminal_screen_passed']
            or spec!=verification.pilot.specifications()[n]):raise ValueError('Require all eight complete retained counter stress failures')
        if (folder/'bench.cir').read_text()!=verification.pilot.fixture(parent,spec,devices[str(spec['guard_um'])]):raise ValueError('Native FF deck changed')
        for name in ['bench.cir','bench.raw']:
            if sha(folder/name)!=r['files'][name]:raise ValueError('Native FF failure witness changed')
        ds=devices[str(spec['guard_um'])];requested={('v('+node.replace(':','.').lower()+')') for d in ds for node in d['terminals'] if node!='0'}
        names,w=validate(folder/'bench.raw',requested,26e-9)
        index={v:i for i,v in enumerate(names)};t=w[:,index['time']]*1e12;zero=np.zeros(len(t))
        def get(node):return zero if node=='0' else w[:,index['v('+node.replace(':','.').lower()+')']]
        report=inspect(t,get,ds)
        failed={d['device'] for d in r['result']['terminal_stress'] if not d['passed']}
        if not report['violations'] or {d['device'] for d in report['violations']}!=failed:raise ValueError('Counter failure is not fully localized to source FFs')
        rows.append(dict(case=n,spec=spec,**report));paths += [folder/name for name in ['summary.json','bench.cir','bench.raw']]
    verification.pilot.bound(parent)
    library=[m['identity']['source_library']]
    if len(library)!=1:raise ValueError('Require exact native FF source library')
    code=[Path(__file__),Path(verification.__file__),Path(verification.pilot.__file__),ROOT/'scripts/native_binary_raw_v2.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code},
        source_library=library[0],source_library_sha256=sha(Path(library[0])))
    out=ROOT/'build/diagnostics/native_ff_reset_guard_targets_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);verification.pilot.atomic(out/'summary.json',dict(identity=identity,rows=rows,
        base_guard_nodes=m['identity']['guard_nodes'],
        added_private_nodes=sorted({node for row in rows for node in row['private_nodes']}-set(m['identity']['guard_nodes'])),
        selected_private_nodes=sorted(set(m['identity']['guard_nodes'])|{node for row in rows for node in row['private_nodes']}),
        all_violations_have_private_candidates=not any(row['uncovered_violations'] for row in rows),qualified_phy=False,
        scope='Regenerated libraries/MOS coverage and complete raw guarded-FF failure localization across eight reset/stop-mode cases; proposed guard nodes only, no repaired-cell or timing proof'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(diagnose(a.artifact.resolve()),flush=True)
