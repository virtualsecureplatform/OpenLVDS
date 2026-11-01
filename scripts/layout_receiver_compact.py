#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build diagnostic compact LVT geometry after the three original DC pilots pass."""
import argparse,fcntl,hashlib,json
from pathlib import Path
import layout_receiver_variant as physical
import receiver_compact_geometry as compact
import receiver_lvt_pair_experiment as source
from receiver_layout_reference import cached

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build(matrix):
    if not matrix.is_relative_to(ROOT/'build/diagnostics/receiver_lvt_pair_matrix'):raise ValueError('Use the selected LVT DC matrix')
    manifest=json.loads((matrix/'manifest.json').read_text());children=manifest['identity']['children'][:3]
    if len(children)!=3 or {(c['process'],c['temperature']) for c in children}!={('tt',25),('sf',40),('fs',40)}:raise ValueError('Require the three original pilots')
    if any(not (ROOT/c['root']/'summary.json').exists() for c in children):raise ValueError('Complete all three DC pilots first')
    proofs={str((matrix/'manifest.json').relative_to(ROOT)):digest(matrix/'manifest.json')}
    for child in children:
        folder=ROOT/child['root']
        if digest(folder/'manifest.json')!=child['manifest_sha256']:raise ValueError('Pilot binding changed')
        report=source.run(folder)
        if not report['lvt_decision_pair']['metrics']['passed']:raise ValueError('DC pilot failed')
        for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn']:proofs[str((folder/n).relative_to(ROOT))]=digest(folder/n)
    text=source.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    metadata=dict(placement='Four folded frontend columns on shared M4 trunks; packed summing/decision/restoration row; critical M3 buses first',
        clamp_variant='unclamped_lvt_pair_compact',diagnostic_stage='three_passing_source_DC_pilots',source_proofs=proofs)
    producers=set(manifest['identity']['code'])|{'layout_receiver_compact.py','receiver_compact_geometry.py','receiver_layout_reference.py'}
    names=producers|{'layout_receiver_variant.py','layout.py','lvs_utils.py','spice_library.py'}
    identity=dict(metadata,source_sha256=hashlib.sha256(text.encode()).hexdigest(),code={n:digest(ROOT/'scripts'/n) for n in sorted(names)})
    out=ROOT/'build/diagnostics/receiver_layout'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=cached(out,identity,text)
        if report is not None:return out,report
        original=physical.draw_macro
        try:
            physical.draw_macro=compact.draw_macro
            actual,report=physical.build(text,metadata,producers)
        finally:physical.draw_macro=original
        if actual!=out or report['identity']!=identity:raise ValueError('Compact physical identity changed')
        files=[out/(TOP+s) for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']]+[out/'candidate.spice',out/'summary.json']
        (out/'physical_cache.json').write_text(json.dumps(dict(files={p.name:digest(p) for p in files}),indent=2)+'\n')
    return out,report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('matrix',type=Path);a=p.parse_args()
    out,report=build(a.matrix.resolve());print(json.dumps(dict(output=str(out),passed=report['passed'])),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
