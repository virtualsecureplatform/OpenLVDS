#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind all 31 fine sections to measured native masks and diagnose junctions.

Unrouted placement diagnostic only. Never rewrites junctions, routes, or admits
an electrical model. A future RC correction still requires actual bank LVS.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import klayout.db as db
import build_measured_balanced_gds_v150 as physical
import prepare_regular_regenerated_placement_v272 as placement
import regular_regenerated_inventory_v277 as inventory
import complete_component_reference_v247 as references
import characterize_standard_references_v250 as standard
import measured_bank_fine_partition_v139 as partition
import extract_moscap_fine_unit_v105 as fine

stock=placement.previous.stock
FINE_VIEWS=stock.VIEWS
FINE=stock.graph_model.FINE
matched_views=stock.matched_views
ROOT=placement.ROOT
sha=placement.sha
VERSION='regular-pair-native-bank-mask-bound-fine-junction-diagnostic-v276.1'
CONTEXT='regular_regenerated_junctions_v276'
MEASUREMENTS=ROOT/'build/diagnostics/moscap_primitive_junctions_v85/787f8642d60dd868'


def standard_reuse(pi,original,si,merged):
    wanted={m:o for m,o in pi['graph']['orders'].items() if m.startswith('sky130_fd_sc_hd__')}
    if si['parent']!=pi['parent'] or si['models']!=wanted or len(wanted)!=5:
        raise ValueError('Standard references do not belong to the exact five-master source placement')
    if any(pi['records'][m]!=original['records'][m] for m in wanted):
        raise ValueError('Reused standard native master record differs from the verified source placement')
    if not all(merged.get(k) is True for k in ('all_native_cell_masks_preserved','all_native_instance_arrays_preserved','all_native_cell_labels_preserved')):
        raise ValueError('Reused native references require identical actual merged masks, hierarchy and labels')
    return dict(source_placement=pi['parent'],models=sorted(wanted),exact_standard_master_records_preserved=True,
                merged_native_masks_hierarchy_and_labels_preserved=True,qualified_phy=False)


def geometry(parent):
    i=placement.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['placement_feasibility_passed'] or r['placement_geometry']['drc_count']!='0'
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged clean exploratory balanced placement')
    vi=matched_views.bound(FINE_VIEWS);name=FINE;spec=vi['specs'][name]
    _,_,measurements=fine.checked(Path(spec['schematic']).parent,MEASUREMENTS)
    primitive=fine.masks(Path(spec['gds']),spec['source_top'],Path(spec['schematic']).read_text(),measurements['rows'],MEASUREMENTS)
    canonical=matched_views.audit(spec,name,parent/'library.gds',parent/'library.lef',i['records'][name])
    hierarchy=physical.native_cells(parent/(i['graph']['top']+'.gds'),parent,i)
    lib=db.Layout();lib.read(str(parent/'library.gds'));active=fine.region(lib,lib.cell(name),(65,20))
    if active.is_empty():raise ValueError('Fine master has no native active geometry')
    names={c['name'] for c in i['plan']['cells'] if c['model']==name}
    if names!={f'u_fine_unit{k}' for k in range(31)}:raise ValueError('Fine placement identities differ')
    placed=[]
    for tag in sorted(names):
        dx,dy=[round(v/lib.dbu) for v in i['plan']['placements'][tag]];region=active.transformed(db.Trans(dx,dy))
        if any(not (region&previous).is_empty() for previous in placed):raise ValueError('Fine-cell active regions merge across instances')
        placed.append(region)
    proof=dict(primitive_masks=primitive,canonical_masks=canonical,bank_native_hierarchy=hierarchy,
               fine_instances=31,native_fine_mos=155,all_fine_active_regions_separate_between_instances=True,
               measured_primitive_junction_geometry_bound=True)
    return i,vi,measurements,proof


def component_reference(parent,standards,pi):
    views=placement.previous.VIEWS;placement.previous.views.bound(views);r=json.loads((views/'summary.json').read_text())
    if (json.loads((views/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or r.get('canonical_component_views_passed') is not True or any(sha(views/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require immutable qualified native integration masters')
    models=[placement.design.DRIVER]
    for model in models:
        p=r['native_qualification'][model]
        if not p['physical']['passed'] or not p['original_native_junctions_preserved']['native_parameters_preserved']:
            raise ValueError('Native component geometry/parameter qualification missing')
    paths=[views/n for n in ('manifest.json','summary.json','state.json',*r['files'])]
    extractions={m:(views/'native'/m/(m+'.lvs.spice')).read_text() for m in models}
    si=standard.bound(standards);sr=json.loads((standards/'summary.json').read_text())
    if (si['parent']!=pi['parent'] or json.loads((standards/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or sr.get('native_standard_references_passed') is not True or any(sha(standards/n)!=h for n,h in sr['files'].items())):
        raise ValueError('Require complete immutable native standard-master references')
    original=json.loads((ROOT/si['parent']/'manifest.json').read_text())['identity']
    merged=json.loads((parent/'summary.json').read_text())['merged_library']
    reuse=standard_reuse(pi,original,si,merged)
    for row in sr['rows']:
        model=row['model'];extractions[model]=(standards/model/row['native_reference_file']).read_text()
    paths += [standards/n for n in ('manifest.json','summary.json','state.json',*sr['files'])]
    reference,proof=references.complete((parent/'reference.spice').read_text(),extractions,json.loads((parent/'manifest.json').read_text())['identity']['graph']['orders'])
    return reference,proof,paths,reuse


def prepare(parent,standards):
    i,vi,mr,proof=geometry(parent);reference,reference_proof,reference_paths,reuse=component_reference(parent,standards,i);r=json.loads((parent/'summary.json').read_text());vr=json.loads((FINE_VIEWS/'summary.json').read_text())
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',*[parent/n for n in r['files']]]
    paths += [FINE_VIEWS/'manifest.json',FINE_VIEWS/'summary.json',*[FINE_VIEWS/n for n in vr['files']],
              MEASUREMENTS/'manifest.json',MEASUREMENTS/'summary.json',*[MEASUREMENTS/n for n in mr['files']]]
    for folder in [Path(vi['specs'][FINE]['schematic']).parent]:
        paths += [p for p in folder.rglob('*') if p.is_file()]
    paths+=reference_paths
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profile='b2_regular_regenerated_p20n16',standard_reference_parent=str(standards.relative_to(ROOT)),standard_reference_reuse=reuse,geometry=proof,component_reference_proof=reference_proof,reference_sha256=hashlib.sha256(reference.encode()).hexdigest(),
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},tools=i['tools'],external_files={**i['external_files'],**vi['external_files']},
                  scope='Fresh ordinary extraction and mask-bound 31-section fine junction allocation diagnostic; no model changes, routes, joint RC or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');(out/'reference.spice').write_text(reference);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or any(sha(Path(t['path']))!=t['sha256'] for t in i['tools'].values())
        or sha(out/'reference.spice')!=i['reference_sha256']):
        raise ValueError('Fine-section junction diagnostic context changed')
    pi=placement.bound(ROOT/i['parent']);return i,pi


def extract(out,parent,pi):
    folder=out/'ordinary';folder.mkdir();name=pi['graph']['top'];file=parent/(name+'.gds')
    lib=db.Layout();lib.read(str(file));commands=['gds readonly false',f'gds read {{{file}}}']
    for cell in lib.each_cell():commands += [f'load {cell.name}',f'save {cell.name}']
    commands += [f'load {name}']
    for index,port in enumerate(pi['graph']['ports'],1):
        x0,y0,x1,y1=pi['plan']['ports'][port]['rect'];x=(x0+x1)/2;y=(y0+y1)/2
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um',f'port make {index}']
    commands += [f'save {name}',f'flatten {name}_flat',f'load {name}_flat','extract all','ext2spice lvs',f'ext2spice -o {name}.lvs.spice {name}_flat.ext']
    stock.assembly.layout.invoke_magic(folder,'\n'.join(commands),'ordinary_fine_sections')
    return re.sub(r'\n[ \t]*\+[ \t]*',' ',(folder/(name+'.lvs.spice')).read_text())


def run(out):
    i,pi=bound(out);parent=ROOT/i['parent'];name=pi['graph']['top']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial fine junction diagnostic')
        (out/'state.json').write_text('{"status":"analyzing","qualified_phy":false}\n')
        text=extract(out,parent,pi);source=(out/'reference.spice').read_text()
        census=inventory.verify(source,name,text,name+'_flat')
        m=json.loads((MEASUREMENTS/'summary.json').read_text());diagnostic=partition.diagnose(text,name+'_flat',m['rows'])
        schematic=partition.identify(source,name)
        if any(diagnostic['partition'][k]!=schematic[k] for k in ['fine_sections','capacitor_mos','programming_mos','guard_mims']):
            raise ValueError('Fine reference and native section census differ')
        bound(out)
        r=dict(analysis_completed=True,geometry=i['geometry'],native_census=census,diagnostic=diagnostic,component_reference_proof=i['component_reference_proof'],standard_reference_reuse=i['standard_reference_reuse'],
               ordinary_extraction_not_per_device_junction_reference=not diagnostic['per_device_capacitor_junctions_match_geometry'],
               parameters_changed=False,original_extraction_preserved=True,whole_bank_native_lvs_passed=False,
               routed=False,joint_rc_qualified=False,electrical_qualification_passed=False,qualified_phy=False,scope=i['scope'])
        r['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","analysis_completed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--standards',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:
        if a.standards is None:p.error('--standards required')
        out=prepare(out,a.standards.resolve());print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
