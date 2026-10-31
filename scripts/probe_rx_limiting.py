#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Probe limiting loaded RX endpoints without qualifying or altering the full matrix."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import characterize_rx_aperture as capture
from rx_candidate_aperture import validate, lease
from rx_aperture_evidence import sha

ROOT=Path(__file__).resolve().parents[1]


def conditions():
    return [dict(process=p,temperature=t,edge='rising',polarity=polarity,clock_slew_ps=200,
        data_slew_ps=20,kind='setup') for p,t in [('ss',0),('ss',40),('sf',40)] for polarity in ['rise','fall']]


def run(parent,wait_slot=None):
    parent=parent.resolve();original=json.loads((parent/'manifest.json').read_text());validate(parent,original)
    identity=dict(parent=str(parent.relative_to(ROOT)),parent_manifest_sha256=sha(parent/'manifest.json'),
        producer_sha256=sha(Path(__file__)),conditions=conditions(),distance_ps=800.)
    root=ROOT/'build/diagnostics/rx_limiting'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=dict(original,conditions=conditions(),diagnostic_request=identity,qualified_phy=False)
        for name,data in [('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode()),
            ('library.spice',(parent/'library.spice').read_bytes()),('requirements.json',(parent/'requirements.json').read_bytes()),
            ('producer.py',Path(__file__).read_bytes())]:
            path=root/name
            if path.exists() and path.read_bytes()!=data:raise ValueError('Limiting RX input changed')
            path.write_bytes(data)
        capture.atomic(root/'state.json',dict(status='running',diagnostic=True,qualified_phy=False))
        results=[]
        for spec in conditions():
            validate(parent,original);capture.validate(root,manifest)
            name=capture.condition_id(spec)
            capture.atomic(root/'execution.json',dict(status='waiting_for_slot',case=name))
            with lease(wait_slot):
                capture.atomic(root/'execution.json',dict(status='running',case=name))
                passed=capture.point(root,manifest,spec,800.)
            validate(parent,original)
            if sha(parent/'manifest.json')!=identity['parent_manifest_sha256'] or sha(Path(__file__))!=identity['producer_sha256']:
                raise ValueError('Limiting RX producer or source manifest changed')
            results.append(dict(case=name,passed=passed,summary_sha256=sha(root/name/'point_800p000000/summary.json')))
            print(name,passed,flush=True)
        capture.atomic(root/'summary.json',dict(diagnostic=True,qualified_phy=False,manifest_sha256=sha(root/'manifest.json'),
            passed=all(r['passed'] for r in results),results=results))
        capture.atomic(root/'state.json',dict(status='complete',diagnostic=True,qualified_phy=False))
    print(root/'summary.json',flush=True)
    return 0 if all(r['passed'] for r in results) else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('aperture',type=Path);p.add_argument('--wait-slot',type=int,choices=range(6));a=p.parse_args()
    raise SystemExit(run(a.aperture,a.wait_slot))
