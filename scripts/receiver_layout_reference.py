# SPDX-License-Identifier: GPL-3.0-only
"""Build immutable placement-only receiver experiments from admitted source/physical evidence."""
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path

import layout_receiver_variant as physical
import layout_receiver_tail_headroom_candidate as tail
from dll_candidate_library import audited

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def device_signature(devices):
    return Counter(json.dumps(d,sort_keys=True) for d in devices)


def reordered(devices,transform):
    before=device_signature(devices)
    result=transform(devices)
    if device_signature(result)!=before:
        raise ValueError('Placement changed receiver devices, parameters or connectivity')
    return result


def cached(out,identity,source):
    path=out/'summary.json'
    if not path.exists():
        if (out/'candidate.spice').exists():raise ValueError('Incomplete geometry; retain it for diagnosis')
        return None
    result=json.loads(path.read_text())
    if result['identity']!=identity or (out/'candidate.spice').read_text()!=source:
        raise ValueError('Captured receiver source or identity changed')
    files=json.loads((out/'physical_cache.json').read_text())['files']
    expected={TOP+s for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']}|{'summary.json','candidate.spice'}
    if set(files)!=expected or any(digest(out/n)!=sha for n,sha in files.items()):
        raise ValueError('Captured receiver physical evidence changed')
    return result


def build(reference,transform,policy,producers):
    if not reference.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use an isolated admitted reduced-tail reference')
    if not isinstance(policy.get('placement'),str) or set(policy)-{'placement','routing_policy','routing_priority'}:
        raise ValueError('Placement policy cannot replace source or admission metadata')
    result=json.loads((reference/'summary.json').read_text());info=json.loads((reference/'extraction.json').read_text())
    meta=result['identity'];source=tail.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    if (not result['passed'] or meta.get('clamp_variant')!='unclamped_tail_headroom' or
            meta.get('decision_tail_width_um')!=16 or meta.get('decision_tail_scale')!=.25 or
            meta.get('replica_monitor_unloaded') is not True or
            meta.get('placement')!='Only six unloaded monitor devices moved before first restoration inverter' or
            meta.get('routing_policy') is not None or
            (reference/'candidate.spice').read_text()!=source or digest(reference/'candidate.spice')!=info['source_sha256']):
        raise ValueError('Expected exact reduced-tail source and original placement')
    for name,sha in meta['code'].items():
        if digest(ROOT/'scripts'/name)!=sha:raise ValueError('Reference receiver producer changed')
    gds=ROOT/result['designs'][TOP]['gds']
    if digest(gds)!=info['gds_sha256']:raise ValueError('Reference receiver GDS changed')
    audited(reference,info)
    if tail.source_gate(ROOT/meta['source_screen'],ROOT/meta['static_screen'])!=meta['source_screen_proofs']:
        raise ValueError('Reference source/DC admission changed')
    metadata={k:v for k,v in meta.items() if k not in ['code','source_sha256']}
    metadata.update(policy,reference_layout=str(reference.relative_to(ROOT)),
                    reference_summary_sha256=digest(reference/'summary.json'),reference_gds_sha256=digest(gds))
    producers=sorted(set(meta['code'])|set(producers)|{Path(__file__).name,'dll_candidate_library.py'})
    names=set(producers)|{'layout_receiver_variant.py','layout.py','lvs_utils.py','spice_library.py'}
    identity=dict(metadata,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  code={n:digest(ROOT/'scripts'/n) for n in sorted(names)})
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ROOT/'build/diagnostics/receiver_layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=cached(out,identity,source)
        if report is not None:return out,report
        original=physical.draw_macro
        def draw(folder,top,ports,devices,library):
            if top!=TOP:raise ValueError('Receiver-only placement experiment')
            return original(folder,top,ports,reordered(devices,transform),library)
        try:
            physical.draw_macro=draw
            actual,report=physical.build(source,metadata,producers)
        finally:physical.draw_macro=original
        if actual!=out or report['identity']!=identity:raise ValueError('Receiver placement identity differs')
        files=[out/(TOP+s) for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']]
        files += [out/'candidate.spice',out/'summary.json']
        (out/'physical_cache.json').write_text(json.dumps(dict(files={p.name:digest(p) for p in files}),indent=2)+'\n')
    return out,report
