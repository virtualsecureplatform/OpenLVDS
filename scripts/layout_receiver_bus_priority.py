#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Change receiver internal bus order without changing devices, placement or bus widths."""
import argparse
import ast
import fcntl
import hashlib
import inspect
import json
from pathlib import Path

import layout
import layout_receiver_variant as physical
import layout_receiver_tail_headroom_candidate as tail
from layout_receiver_input_island import cached, digest
from dll_candidate_library import audited

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
SENSITIVE=['PP','PN','CO','CL','CT','NL','NR','PL','PR']


def bus_order(ports,internal):
    first=[TOP+'__'+leaf for leaf in SENSITIVE]
    if not set(first)<=set(internal):raise ValueError('Missing receiver sensitive routing nets')
    if set(ports)&set(internal):raise ValueError('Internal routing changes a public port')
    return list(ports)+first+sorted(set(internal)-set(first))


def router_tree(source):
    """Specialize one guarded assignment in the captured drawing producer."""
    tree=ast.parse(source)
    nodes=[n for n in ast.walk(tree) if isinstance(n,ast.Assign) and
           any(isinstance(t,ast.Name) and t.id=='net_order' for t in n.targets)]
    expected=ast.parse('list(ports)+sorted(internal,key=priority if compact_internal else None)',mode='eval').body
    if len(nodes)!=1 or ast.dump(nodes[0].value)!=ast.dump(expected):
        raise ValueError('Unexpected original internal routing assignment')
    nodes[0].value=ast.parse('_receiver_bus_order(ports,internal)',mode='eval').body
    return ast.fix_missing_locations(tree)


def router():
    # Every other drawing statement, including device transforms and widths,
    # is inherited verbatim. Both this specialization and layout.py are captured.
    tree=router_tree(inspect.getsource(layout.draw_macro))
    scope=dict(layout.__dict__);scope['_receiver_bus_order']=bus_order
    exec(compile(tree,__file__,'exec'),scope)
    return scope['draw_macro']


def build(reference):
    if not reference.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use an isolated admitted reduced-tail reference')
    report=json.loads((reference/'summary.json').read_text());info=json.loads((reference/'extraction.json').read_text())
    meta=report['identity'];source=tail.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    if (not report['passed'] or meta.get('clamp_variant')!='unclamped_tail_headroom' or
            meta.get('decision_tail_width_um')!=16 or meta.get('decision_tail_scale')!=.25 or
            meta.get('placement')!='Only six unloaded monitor devices moved before first restoration inverter' or
            meta.get('routing_policy') is not None or
            (reference/'candidate.spice').read_text()!=source or digest(reference/'candidate.spice')!=info['source_sha256']):
        raise ValueError('Expected the original reduced-tail placement and exact admitted source')
    for name,stamp in meta['code'].items():
        if digest(ROOT/'scripts'/name)!=stamp:raise ValueError('Reference receiver producer changed')
    gds=ROOT/report['designs'][TOP]['gds']
    if digest(gds)!=info['gds_sha256']:raise ValueError('Reference receiver GDS changed')
    audited(reference,info)
    if tail.source_gate(ROOT/meta['source_screen'],ROOT/meta['static_screen'])!=meta['source_screen_proofs']:
        raise ValueError('Reference source/DC admission changed')
    metadata={k:v for k,v in meta.items() if k not in ['code','source_sha256']}
    metadata.update(routing_priority=SENSITIVE,routing_policy='Sensitive internal buses first; unchanged device placement, bus widths and public pins',
                    reference_layout=str(reference.relative_to(ROOT)),reference_summary_sha256=digest(reference/'summary.json'),
                    reference_gds_sha256=digest(gds))
    producers=sorted(set(meta['code'])|{Path(__file__).name,'layout_receiver_input_island.py','dll_candidate_library.py'})
    names=set(producers)|{'layout_receiver_variant.py','layout.py','lvs_utils.py','spice_library.py'}
    identity=dict(metadata,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  code={n:digest(ROOT/'scripts'/n) for n in sorted(names)})
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ROOT/'build/diagnostics/receiver_layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=cached(out,identity,source)
        if result is not None:return out,result
        original=physical.draw_macro;draw_router=router()
        def draw(folder,top,ports,devices,library):
            if top!=TOP:raise ValueError('Receiver-only routing specialization')
            return draw_router(folder,top,ports,tail.place_monitor(devices),library)
        try:
            physical.draw_macro=draw
            actual,result=physical.build(source,metadata,producers)
        finally:physical.draw_macro=original
        if actual!=out or result['identity']!=identity:raise ValueError('Receiver routing identity differs')
        paths=[out/(TOP+s) for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']]
        paths += [out/'candidate.spice',out/'summary.json']
        (out/'physical_cache.json').write_text(json.dumps(dict(files={p.name:digest(p) for p in paths}),indent=2)+'\n')
    return out,result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('reference',type=Path);args=parser.parse_args()
    out,report=build(args.reference.resolve())
    print(json.dumps(dict(output=str(out),passed=report['passed'])),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
