#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Stream a completed isolated-bank route and require native masks, DRC and LVS."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import klayout.db as db
import route_isolated_fine_bank_v242 as route
import build_measured_balanced_gds_v150 as original
import build_parallel_output_cell_v111 as native_qualifier
import isolated_fine_bank_inventory_v244 as inventory

ROOT=route.ROOT
sha=route.sha
VERSION='isolated-fine-routed-native-masks-hierarchy-drc-lvs-v253.1'
CONTEXT='isolated_fine_native_gds_v253'
SCOPE='Completed gated isolated-bank route, restored exact native masks/hierarchy/placement, fresh DRC/LVS and strict native parameters; shared-wire RC, periodic/PVT, clock-chain and PHY remain unqualified'


def require_route(state,report):
    if (state!=dict(status='complete',passed=True,qualified_phy=False)
        or report.get('route_bringup_passed') is not True or report.get('returncode')!=0
        or report.get('router_final_violations')!=0 or not report.get('connection_and_coverage_check')):
        raise ValueError('Require complete passing zero-violation isolated native route')


def reference_contract(text,graph):
    defs=inventory.native.layout.circuits(text)
    if graph['top'] not in defs or defs[graph['top']][0]!=graph['ports']:
        raise ValueError('Native reference public interface differs from graph')
    if any(model not in defs or defs[model][0]!=order for model,order in graph['orders'].items()):
        raise ValueError('Native master definition order differs from graph instance order')
    calls={}
    for name,nodes,model,params in defs[graph['top']][1]:
        if params or model not in graph['orders'] or len(nodes)!=len(graph['orders'][model]) or name in calls:
            raise ValueError('Invalid native root component reference')
        calls[name]=(model,dict(zip(graph['orders'][model],nodes)))
    expected={c['native_name']:(c['model'],c['pins']) for c in graph['cells']}
    if len(expected)!=180 or calls!=expected:raise ValueError('Native reference component pin/net graph differs')
    return dict(all_180_root_component_calls_and_named_nets_verified=True,all_native_master_port_orders_verified=True)


def validate(parent):
    state=json.loads((parent/'state.json').read_text());r=json.loads((parent/'summary.json').read_text())
    require_route(state,r);ri,ii,pi=route.bound(parent)
    if (any(sha(parent/n)!=h for n,h in r['files'].items())
        or route.check(parent,ri,ii)!=r['connection_and_coverage_check']):
        raise ValueError('Native route outputs or connection/coverage proof changed')
    reference=(ROOT/ri['native_reference']).read_text();proof=reference_contract(reference,pi['graph'])
    return ri,pi,r,proof


def prepare(parent):
    ri,pi,r,proof=validate(parent);tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/klayout'
    lyts=list(tech.rglob('sky130A.lyt'));maps=list(tech.rglob('sky130A.map'))
    if len(lyts)!=1 or len(maps)!=1:raise ValueError('Require exact SKY130 streamout technology/map')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]+[ROOT/n for n in ri['inputs']]
    paths+=[ROOT/ri['native_reference']]
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),placement=ri['placement'],native_reference=ri['native_reference'],
        reference_contract=proof,lyt=str(lyts[0]),mapping=str(maps[0]),inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},
        external_files={str(p):sha(p) for p in [lyts[0],maps[0]]},scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())):
        raise ValueError('Isolated routed native GDS context changed')
    ri,pi,_,proof=validate(ROOT/i['parent'])
    if ri['placement']!=i['placement'] or ri['native_reference']!=i['native_reference'] or proof!=i['reference_contract']:
        raise ValueError('Isolated native GDS route/reference changed')
    return i,pi


def run(out):
    i,pi=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial isolated routed GDS')
        (out/'state.json').write_text('{"status":"qualifying_native_gds","qualified_phy":false}\n')
        parent=ROOT/i['parent'];placed=ROOT/i['placement'];top=pi['graph']['top']
        mask=hierarchy=physical=parameters=final_mask=final_hierarchy=None;error=None
        try:
            file=original.legacy.stream(out,parent,dict(pi,parent=i['placement']),Path(i['lyt']),Path(i['mapping']))
            mask=original.legacy.masks(file,placed/(top+'.gds'),top,pi['plan']['die'])
            hierarchy=original.native_cells(file,placed,pi)
            reference=(ROOT/i['native_reference']).read_text()
            physical,_=native_qualifier.qualify(out,file,pi['graph'],pi['plan'],reference)
            actual=re.sub(r'\n[ \t]*\+[ \t]*',' ',(out/'native'/(top+'.lvs.spice')).read_text())
            parameters=inventory.verify(reference,top,actual,top+'_flat')
            if parameters['newly_characterized_junction_devices']!=155:raise ValueError('Only original fine junctions may remain separately geometry-bound')
            final=ROOT/physical['gds'];final_mask=original.legacy.masks(final,placed/(top+'.gds'),top,pi['plan']['die'])
            final_hierarchy=original.native_cells(final,placed,pi)
        except Exception as e:error=type(e).__name__+': '+str(e)
        bound(out);passed=bool(error is None and mask and hierarchy and physical and parameters and final_mask and final_hierarchy)
        r=dict(native_routed_gds_passed=passed,physical=physical,native_parameters=parameters,mask_proof=mask,native_hierarchy_proof=hierarchy,
            final_mask_proof=final_mask,final_native_hierarchy_proof=final_hierarchy,reference_contract=i['reference_contract'],error=error,
            joint_rc_extracted=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
        r['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
