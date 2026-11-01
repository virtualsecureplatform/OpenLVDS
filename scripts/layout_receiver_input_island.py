#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Localize receiver input mirrors/loads before the decision stage, preserving its circuit."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import re

import layout_receiver_variant as physical
import layout_receiver_tail_headroom_candidate as tail
from dll_candidate_library import audited

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
MIRRORS=['XNML','XNMR','XPML','XPMR']
LOADS=['XRLPP'+branch for branch in 'ABCDE']+['XRLPN'+branch for branch in 'ABCDE']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def logical(device):
    name=device['name']
    if not name.startswith(TOP+'__'):raise ValueError('Unexpected receiver device hierarchy')
    return re.sub(r'_F\d+$','',name[len(TOP)+2:].split('__')[0])


def place(devices):
    base=tail.place_monitor(devices)
    members=set(MIRRORS+LOADS)
    island=[d for d in base if logical(d) in members]
    expected=Counter({name:2 for name in MIRRORS})+Counter({name:1 for name in LOADS})
    if Counter(logical(d) for d in island)!=expected:
        raise ValueError('Unexpected input mirror/load finger coverage')
    rest=[d for d in base if logical(d) not in members]
    anchors=[i for i,d in enumerate(rest) if logical(d)=='XPCB']
    if len(anchors)!=1:raise ValueError('Expected the original decision-bias anchor')
    index=anchors[0]
    return rest[:index]+island+rest[index:]


def cached(out,identity,source):
    summary=out/'summary.json'
    if not summary.exists():
        if (out/'candidate.spice').exists():raise ValueError('Incomplete geometry; retain it for diagnosis')
        return None
    report=json.loads(summary.read_text())
    if report['identity']!=identity or (out/'candidate.spice').read_text()!=source:
        raise ValueError('Captured input-island source or identity changed')
    files=json.loads((out/'physical_cache.json').read_text())['files']
    required={TOP+s for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']}|{'summary.json','candidate.spice'}
    if set(files)!=required or any(digest(out/n)!=h for n,h in files.items()):
        raise ValueError('Captured input-island physical evidence changed')
    return report


def build(reference):
    if not reference.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use an isolated reduced-tail receiver reference')
    report=json.loads((reference/'summary.json').read_text());info=json.loads((reference/'extraction.json').read_text())
    meta=report['identity'];source=tail.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    if (not report['passed'] or meta.get('clamp_variant')!='unclamped_tail_headroom' or
            meta.get('decision_tail_width_um')!=16 or meta.get('decision_tail_scale')!=.25 or
            (reference/'candidate.spice').read_text()!=source or digest(reference/'candidate.spice')!=info['source_sha256']):
        raise ValueError('Expected the exact admitted reduced-tail source')
    for name,stamp in meta['code'].items():
        if digest(ROOT/'scripts'/name)!=stamp:raise ValueError('Reference receiver producer changed')
    gds=ROOT/report['designs'][TOP]['gds']
    if digest(gds)!=info['gds_sha256']:raise ValueError('Reference receiver GDS changed')
    audited(reference,info)
    if tail.source_gate(ROOT/meta['source_screen'],ROOT/meta['static_screen'])!=meta['source_screen_proofs']:
        raise ValueError('Reference receiver source/DC admission changed')
    metadata={k:v for k,v in meta.items() if k not in ['code','source_sha256']}
    metadata.update(placement='Local input mirror/load island immediately before unchanged decision stage',
                    reference_layout=str(reference.relative_to(ROOT)),reference_summary_sha256=digest(reference/'summary.json'),
                    reference_gds_sha256=digest(gds))
    producers=sorted(set(meta['code'])|{Path(__file__).name,'dll_candidate_library.py'})
    names=set(producers)|{'layout_receiver_variant.py','layout.py','lvs_utils.py','spice_library.py'}
    identity=dict(metadata,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  code={n:digest(ROOT/'scripts'/n) for n in sorted(names)})
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ROOT/'build/diagnostics/receiver_layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=cached(out,identity,source)
        if result is not None:return out,result
        original=physical.draw_macro
        def draw(folder,top,ports,devices,library):
            if top!=TOP:raise ValueError('Expected the receiver macro')
            return original(folder,top,ports,place(devices),library)
        try:
            physical.draw_macro=draw
            actual,result=physical.build(source,metadata,producers)
        finally:physical.draw_macro=original
        if actual!=out or result['identity']!=identity:raise ValueError('Input-island physical identity differs')
        paths=[out/(TOP+s) for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']]
        paths += [out/'candidate.spice',out/'summary.json']
        (out/'physical_cache.json').write_text(json.dumps(dict(files={p.name:digest(p) for p in paths}),indent=2)+'\n')
    return out,result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('reference',type=Path);args=parser.parse_args()
    out,report=build(args.reference.resolve())
    print(json.dumps(dict(output=str(out),passed=report['passed'])),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
