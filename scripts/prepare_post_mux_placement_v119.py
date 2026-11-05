#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check post-mux graph/placement with real masters while timing runs separately.

This is an exploratory placement artifact, never a timing-candidate admission.
It does not route, extract common RC, update a registry or select a PHY.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import klayout.db as db
import build_tg_bank_floorplan_v49 as assembly
import build_clock_cell_views_v114 as views
import post_mux_bank_physical_v118 as design
from audit_rc_comments_v2 import collapse

ROOT=assembly.ROOT
sha=assembly.sha
VERSION='post-mux-real-master-graph-and-placement-feasibility-v119.1'
CONTEXT='post_mux_placement_v119'
REGISTRY=ROOT/'build/diagnostics/bank_cell_registry_verification_v48/b1813242cd69dc23'
VIEWS=ROOT/'build/diagnostics/clock_cell_views_v114/5c1222c9bf8bb27b'


def candidate(parent,copies):
    module={1:'probe_post_mux_output_rc_v113',2:'probe_parallel_post_mux_roots_v117'}[copies]
    code='import sys,json,importlib;from pathlib import Path;sys.path.insert(0,"scripts");p=importlib.import_module(sys.argv[1]);print(json.dumps(p.bound(Path(sys.argv[2])),sort_keys=True))'
    p=subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,module,str(parent)],cwd=ROOT,capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


def inputs(parent,copies):
    m=candidate(parent,copies);oldlib,pi,before,oldrecords=assembly.inputs(REGISTRY)
    vi=views.bound(VIEWS);vr=json.loads((VIEWS/'summary.json').read_text())
    if (json.loads((VIEWS/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not vr['canonical_component_views_passed'] or any(sha(VIEWS/n)!=h for n,h in vr['files'].items())):
        raise ValueError('Require complete canonical component view proofs')
    records={**oldrecords,**vr['cells']}
    if len(records)!=14 or set(oldrecords)&set(vr['cells']):raise ValueError('Canonical library additions collide')
    g=design.graph(before,copies);plan=design.placement(before,g,records,copies)
    refs=[(VIEWS/'native'/model/(model+'.sch.spice')).read_text() for model in vr['cells']]
    text=(ROOT/pi['graph_parent']/'bank.sch.spice').read_text();reference=design.native_source(g,text,refs,records)
    component=(parent/'bank_w126.spice').read_text()
    top=design.original.native.definitions(component)
    top=next(n for n in top if n.startswith('openlvds_') and n.endswith('_v116' if copies==2 else '_v112'))
    proof=design.compare_component(g,component,top)
    # Collapse every definition in its own local namespace. Numeric wire-node
    # names in different subcircuits must never be joined together.
    flat=''.join(collapse(design.cell_definition(component,n)) for n in design.original.native.definitions(component))
    inventory=design.dimension_inventory(reference,g['top'])
    if inventory!=design.dimension_inventory(flat,top):
        raise ValueError('Physical reference native dimensions differ from measured component model')
    mos=sum(n for (m,w,l),n in inventory.items() if 'fet_' in m);mim=sum(n for (m,w,l),n in inventory.items() if 'cap_mim' in m)
    if (mos,mim)!=(981+8*(copies-1),35):raise ValueError('Native physical placement census changed')
    proof.update(native_dimensions_and_inventory_preserved=True,native_mos=mos,native_mims=mim)
    return m,oldlib,pi,vi,records,g,plan,reference,proof


def prepare(parent,copies):
    m,oldlib,pi,vi,records,g,plan,reference,proof=inputs(parent,copies)
    paths=[parent/'manifest.json',parent/'bank_w126.spice',*[ROOT/n for n in m['identity']['inputs']],
           REGISTRY/'manifest.json',REGISTRY/'summary.json',oldlib/'manifest.json',oldlib/'summary.json',
           VIEWS/'manifest.json',VIEWS/'summary.json',VIEWS/'state.json']
    for folder in [REGISTRY,oldlib,VIEWS]:
        r=json.loads((folder/'summary.json').read_text());paths += [folder/n for n in r['files']]
    code=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),copies=copies,library_parent=str(oldlib.relative_to(ROOT)),
           component_views=str(VIEWS.relative_to(ROOT)),graph=g,plan=plan,records=records,graph_proof=proof,
           reference_sha256=hashlib.sha256(reference.encode()).hexdigest(),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={str(p.relative_to(ROOT)):sha(p) for p in code},
           external_files={**pi['external_files'],**vi['external_files']},openroad=pi['openroad'],tech_lef=pi['tech_lef'],
           tools=vi['tools'],klayout=vi['klayout'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n')
    (out/'reference.spice').write_text(reference);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or any(sha(Path(t['path']))!=t['sha256'] for t in [i['openroad'],*i['tools'].values()])
        or i['klayout']!=dict(version=db.__version__,module_sha256=sha(Path(db.__file__)))
        or sha(out/'reference.spice')!=i['reference_sha256']):raise ValueError('Post-mux placement inputs changed')
    return i


def merge(out,i):
    old=ROOT/i['library_parent'];new=ROOT/i['component_views'];a=db.Layout();a.read(str(old/'library.gds'))
    b=db.Layout();b.read(str(new/'library.gds'))
    if a.dbu!=.001 or b.dbu!=a.dbu or {c.name for c in a.each_cell()}&{c.name for c in b.each_cell()}:
        raise ValueError('Merged library scale or hierarchy names collide')
    a.read(str(new/'library.gds'));a.write(str(out/'library.gds'))
    original=(old/'library.lef').read_text();added=(new/'library.lef').read_text()
    lef='VERSION 5.7 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\n'
    lef+=''.join(views.adapter.macro(original if model in json.loads((old/'summary.json').read_text())['cells'] else added,model) for model in i['records'])
    (out/'library.lef').write_text(lef+'END LIBRARY\n')
    fresh=db.Layout();fresh.read(str(out/'library.gds'))
    if {c.name for c in fresh.each_cell()}!={c.name for c in a.each_cell()}:raise ValueError('Stored merged library hierarchy changed')
    for model in i['records']:
        source=old if model in json.loads((old/'summary.json').read_text())['cells'] else new
        lib=db.Layout();lib.read(str(source/'library.gds'));src=lib.cell(model);dst=fresh.cell(model)
        if src is None or dst is None:raise ValueError('Missing merged physical master')
        keys={(l.get_info(k).layer,l.get_info(k).datatype) for l in [lib,fresh] for k in l.layer_indexes()}
        for key in keys:
            if not (views.registry.region(db,lib,src,key)^views.registry.region(db,fresh,dst,key)).is_empty():
                raise ValueError('Merged physical master masks changed')
    return views.registry.check_opendb(out,i,i['records'])


def run(out):
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial post-mux placement')
        (out/'state.json').write_text('{"status":"placing","qualified_phy":false}\n')
        merged=merge(out,i);g=i['graph'];plan=i['plan']
        placed=assembly.opendb(out,dict(i,_parent=str(out.relative_to(ROOT))),g,plan)
        file=assembly.gds(out,out,g,plan)
        buses=design.fixed_bus_audit(file,g,plan,i['records']);geometry=assembly.drc(out,file,g['top'])
        passed=geometry['placement_and_fixed_bus_drc_passed'];bound(out)
        report=dict(graph=i['graph_proof'],merged_library=merged,placement=placed,fixed_buses=buses,placement_geometry=geometry,
                    placement_feasibility_passed=passed,routed=False,joint_rc_extracted=False,
                    timing_candidate_admitted=False,electrical_qualification_passed=False,qualified_phy=False)
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--root-copies',type=int,choices=[1,2],default=2)
    a=p.parse_args();out=prepare(a.artifact.resolve(),a.root_copies) if a.action in ['prepare','campaign'] else a.artifact.resolve();print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
