#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Explore real-master balanced-bank placement while native timing runs.

No routing, bank LVS/joint RC, profile selection or electrical/PHY admission.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import klayout.db as db
import build_tg_bank_floorplan_v49 as assembly
import build_clock_cell_views_v114 as original_views
import build_matched_clock_cell_views_v124 as matched_views
import balanced_physical_graph_v126 as graph_model
import balanced_bank_placement_v128 as design

ROOT=assembly.ROOT
sha=assembly.sha
VERSION='measured-balanced-gangs-real-master-placement-feasibility-v129.1'
CONTEXT='balanced_placement_v129'
REGISTRY=ROOT/'build/diagnostics/bank_cell_registry_verification_v48/b1813242cd69dc23'
PAIR=ROOT/'build/diagnostics/clock_cell_views_v114/5c1222c9bf8bb27b'
VIEWS=ROOT/'build/diagnostics/clock_cell_views_v124/3557a1acd9b9ad4c'


def candidate(parent,profile):
    code='''import sys,json
from pathlib import Path
sys.path.insert(0,"scripts")
import probe_strong_coarse_bank_v123 as p
import measured_gang_bank_v125 as c
parent=Path(sys.argv[1]);profile=sys.argv[2];m=p.bound(parent)
bank=c.transform_existing((parent/("bank_"+profile+".spice")).read_text(),profile)
files=[str(f.relative_to(c.ROOT)) for f in c.driver_inputs()]
files += sorted({str(Path(mod.__file__).resolve().relative_to(c.ROOT)) for mod in list(sys.modules.values()) if getattr(mod,"__file__",None) and Path(mod.__file__).resolve().parent==c.ROOT/"scripts"})
print(json.dumps(dict(manifest=m,bank=bank,files=files),sort_keys=True))
'''
    p=subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(parent),profile],cwd=ROOT,capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


def inputs(parent,profile):
    c=candidate(parent,profile);oldlib,pi,before,oldrecords=assembly.inputs(REGISTRY)
    reports=[];external=dict(pi['external_files'])
    for folder,producer in [(PAIR,original_views),(VIEWS,matched_views)]:
        i=producer.bound(folder);r=json.loads((folder/'summary.json').read_text())
        if (json.loads((folder/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
            or not r['canonical_component_views_passed'] or any(sha(folder/n)!=h for n,h in r['files'].items())):
            raise ValueError('Require unchanged canonical measured master qualifications')
        reports.append(r);external.update(i['external_files'])
    records=dict(oldrecords)
    for r in reports:
        if set(records)&set(r['cells']):raise ValueError('Canonical measured master names collide')
        records.update(r['cells'])
    if len(records)!=17:raise ValueError('Measured balanced library master inventory changed')
    g=graph_model.graph(before,profile);plan=design.placement(before,g,records,profile)
    libraries=[(ROOT/pi['graph_parent']/'bank.sch.spice').read_text()]
    for folder,masters in [(PAIR,[graph_model.PAIR]),(VIEWS,[graph_model.FINE,graph_model.coarse(profile)])]:
        libraries += [(folder/'native'/m/(m+'.sch.spice')).read_text() for m in masters]
    reference=graph_model.native_source(g,libraries);top='openlvds_measured_gangs_'+profile+'_v125'
    proof=graph_model.compare_component(g,c['bank'],top,profile)
    proof.update(graph_model.native_inventory_proof(g,reference,c['bank'],top,profile))
    return c,oldlib,pi,records,g,plan,reference,proof,external


def prepare(parent,profile):
    c,oldlib,pi,records,g,plan,reference,proof,external=inputs(parent,profile)
    paths=[parent/'manifest.json',parent/('bank_'+profile+'.spice'),*[ROOT/n for n in c['manifest']['identity']['inputs']],*[ROOT/n for n in c['files']]]
    for folder in [REGISTRY,oldlib,PAIR,VIEWS]:
        r=json.loads((folder/'summary.json').read_text());paths += [folder/'manifest.json',folder/'summary.json',*[folder/n for n in r['files']]]
    code=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profile=profile,library_parents=[str(f.relative_to(ROOT)) for f in [oldlib,PAIR,VIEWS]],
           graph=g,plan=plan,records=records,graph_proof=proof,reference_sha256=hashlib.sha256(reference.encode()).hexdigest(),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={str(p.relative_to(ROOT)):sha(p) for p in code},
           external_files=external,openroad=pi['openroad'],tech_lef=pi['tech_lef'],tools=pi['tools'],klayout=pi['klayout'])
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
        or sha(out/'reference.spice')!=i['reference_sha256']):raise ValueError('Balanced placement inputs changed')
    return i


def own_masks(lib,cell,key):
    index=lib.find_layer(*key)
    return db.Region() if index is None else db.Region(cell.shapes(index)).merged()


def own_labels(lib,cell):
    return sorted((lib.get_info(k).layer,lib.get_info(k).datatype,s.text.string,s.text.trans.to_s())
                  for k in lib.layer_indexes() for s in cell.shapes(k).each() if s.is_text())


def hierarchy(lib,cell):
    return Counter((lib.cell(x.cell_index).name,x.cplx_trans.to_s(),x.a.x,x.a.y,x.b.x,x.b.y,x.na,x.nb) for x in cell.each_inst())


def audit_cell(source,a,target,b):
    if hierarchy(source,a)!=hierarchy(target,b) or own_labels(source,a)!=own_labels(target,b):
        raise ValueError('Merged native instances or labels changed')
    keys={(lib.get_info(k).layer,lib.get_info(k).datatype) for lib in [source,target] for k in lib.layer_indexes()}
    for key in keys:
        if not (own_masks(source,a,key)^own_masks(target,b,key)).is_empty():raise ValueError('Merged native cell masks changed')


def negative_controls(out):
    source=db.Layout();source.read(str(PAIR/'library.gds'));a=source.cell(graph_model.PAIR)
    folder=out/'negative_controls';folder.mkdir();rows=[]
    for fault in ['extra_mask','changed_port_label','duplicate_native_instance']:
        bad=db.Layout();bad.read(str(out/'library.gds'));b=bad.cell(graph_model.PAIR)
        if fault=='extra_mask':
            box=b.bbox();b.shapes(bad.layer(70,20)).insert(db.Box(box.right+1000,box.top+1000,box.right+1100,box.top+1100))
        elif fault=='changed_port_label':
            shape=next(x for x in b.shapes(bad.find_layer(70,5)).each() if x.is_text())
            label=shape.text;label.string='CORRUPTED_PORT';shape.text=label
        else:
            first=next(b.each_inst());b.insert(db.CellInstArray(first.cell_index,first.trans))
        bad.write(str(folder/(fault+'.gds')))
        try:audit_cell(source,a,bad,b)
        except ValueError as e:rows.append(dict(fault=fault,rejected=True,reason=str(e)))
        else:raise ValueError('Merged-library corruption was accepted: '+fault)
    (folder/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
    return rows


def merge(out,i):
    combined=db.Layout();combined.dbu=.001;names=set();sources={};lefs={}
    for relative in i['library_parents']:
        parent=ROOT/relative;lib=db.Layout();lib.read(str(parent/'library.gds'));incoming={c.name for c in lib.each_cell()}
        if lib.dbu!=.001 or names&incoming:raise ValueError('Merged balanced library scale/hierarchy collision')
        names|=incoming;combined.read(str(parent/'library.gds'))
        report=json.loads((parent/'summary.json').read_text());text=(parent/'library.lef').read_text()
        for model in report['cells']:
            if model in sources:raise ValueError('Duplicate merged balanced master')
            sources[model]=parent;lefs[model]=original_views.adapter.macro(text,model)
    combined.write(str(out/'library.gds'))
    (out/'library.lef').write_text('VERSION 5.7 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\n'+''.join(lefs[m] for m in i['records'])+'END LIBRARY\n')
    fresh=db.Layout();fresh.read(str(out/'library.gds'))
    if names!={c.name for c in fresh.each_cell()}:raise ValueError('Stored balanced library hierarchy changed')
    for relative in i['library_parents']:
        lib=db.Layout();lib.read(str(ROOT/relative/'library.gds'))
        for a in lib.each_cell():audit_cell(lib,a,fresh,fresh.cell(a.name))
    opendb=original_views.registry.check_opendb(out,i,i['records'])
    return dict(opendb=opendb,all_native_cell_masks_preserved=True,all_native_instance_arrays_preserved=True,all_native_cell_labels_preserved=True,negative_controls=negative_controls(out))


def run(out):
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial balanced placement')
        (out/'state.json').write_text('{"status":"placing","qualified_phy":false}\n')
        merged=merge(out,i);g=i['graph'];plan=i['plan']
        placed=assembly.opendb(out,dict(i,_parent=str(out.relative_to(ROOT))),g,plan)
        file=assembly.gds(out,out,g,plan)
        buses=design.fixed_bus_audit(file,g,plan,i['records']);geometry=assembly.drc(out,file,g['top'])
        bound(out);passed=geometry['placement_and_fixed_bus_drc_passed']
        report=dict(profile=i['profile'],graph=i['graph_proof'],merged_library=merged,placement=placed,fixed_buses=buses,placement_geometry=geometry,
                    placement_feasibility_passed=passed,root_outputs_routed=False,routed=False,joint_rc_extracted=False,timing_candidate_admitted=False,
                    electrical_qualification_passed=False,qualified_phy=False)
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--profile',choices=['b2','b3'],default='b2');a=p.parse_args()
    out=prepare(a.artifact.resolve(),a.profile) if a.action in ['prepare','campaign'] else a.artifact.resolve();print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
