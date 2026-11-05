#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify native coarse buffer gangs with all junctions and connecting RC."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import klayout.db as db
import build_tg_bank_floorplan_v49 as assembly
import build_tg_bank_gds_v51 as native
import verify_tg_bank_joint_rc_v52 as math_proof
import extract_native_flat_v4 as extractor
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from lvs_utils import strict_setup,clean_match
from reduce_rc import reduce_netlist
import parallel_coarse_cell_v120 as cells

ROOT=assembly.ROOT
sha=assembly.sha
VERSION='parallel-native-coarse-buffers-gds-junctions-and-full-component-rc-v121.1'
CONTEXT='parallel_coarse_cells_v121'


def inputs(registry):
    parent,pi,_,records=assembly.inputs(registry)
    library=(ROOT/pi['graph_parent']/'bank.sch.spice').read_text()
    designs={}
    for profile in cells.COPIES:
        graph,plan=cells.design(profile,records)
        designs[profile]=dict(graph=graph,plan=plan,reference=cells.reference(graph,library))
    return parent,pi,designs


def prepare(registry):
    parent,pi,designs=inputs(registry);r=json.loads((registry/'summary.json').read_text())
    paths=[registry/'manifest.json',registry/'summary.json',*[registry/n for n in r['files']],
           parent/'manifest.json',parent/'summary.json',*[parent/n for n in json.loads((parent/'summary.json').read_text())['files']]]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,registry=str(registry.relative_to(ROOT)),library=str(parent.relative_to(ROOT)),designs=designs,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},math_runtime=math_proof.math_proof()['runtime'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or math_proof.math_proof()['runtime']!=i['math_runtime']):raise ValueError('Tapped output component context changed')
    parent,pi,designs=inputs(ROOT/i['registry'])
    if str(parent.relative_to(ROOT))!=i['library'] or json.loads(json.dumps(designs))!=i['designs']:
        raise ValueError('Tapped output component geometry cannot regenerate')
    return i,pi


def qualify(folder,file,graph,plan,reference):
    name=graph['top'];target=folder/'native';target.mkdir();(target/(name+'.sch.spice')).write_text(reference)
    lib=db.Layout();lib.read(str(file));commands=['gds readonly false',f'gds read {{{file}}}']
    for cell in lib.each_cell():commands += [f'load {cell.name}',f'save {cell.name}']
    commands += [f'load {name}']
    for index,port in enumerate(graph['ports'],1):
        a,b,c,d=plan['ports'][port]['rect'];x=(a+c)/2;y=(b+d)/2
        commands += [f'box values {x-.05}um {y-.05}um {x+.05}um {y+.05}um',f'port make {index}']
    commands += [f'save {name}'];assembly.layout.invoke_magic(target,'\n'.join(commands),'import_tapped')
    result=assembly.layout.qualify(target,name)
    if not result['passed']:raise ValueError('Tapped output GDS DRC or native LVS failed')
    _,expected=native.native_leaves(reference,name)
    _,actual=native.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',(target/(name+'.lvs.spice')).read_text()),name+'_flat')
    params=native.inventory.compare_parameters(expected,actual)
    return result,params


def certify(folder,info,name,reference,expected_count):
    raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist'];regenerated=folder/'regenerated.spice'
    if not info['passed'] or not audit(raw.read_text())['elementwise_passive_passed']:
        raise ValueError('Tapped output RC extraction failed')
    if reduce_netlist(raw,regenerated)!=info['reduction'] or sha(regenerated)!=info['netlist_sha256']:
        raise ValueError('Tapped output RC reduction cannot regenerate')
    proof=math_proof.math_proof(raw,reduced)
    if not proof['proof']['passed']:raise ValueError('Tapped output Schur terminal-current proof failed')
    flat=folder/'wire_collapsed.spice';flat.write_text(collapse(reduced.read_text()))
    _,expected=native.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',reference.read_text()),name+'_flat')
    _,actual=native.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',flat.read_text()),name)
    params=native.inventory.compare_parameters(expected,actual)
    if params['native_primitives']!=expected_count:raise ValueError('Tapped output native RC inventory changed')
    setup=strict_setup(folder/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
    p=subprocess.run(['netgen','-batch','lvs',f'{flat} {name}',f'{reference} {name}_flat',str(setup),str(folder/'rc_lvs.log')],cwd=folder,capture_output=True,text=True)
    (folder/'rc_lvs_console.log').write_text(p.stdout+p.stderr)
    if not clean_match((folder/'rc_lvs.log').read_text(),p.returncode):raise ValueError('Tapped output collapsed native RC topology changed')
    return dict(component_rc_passed=True,native_parameters=params,independent_terminal_current_witness=proof,
                exact_reduction_regenerated=True,native_topology_verified=True,qualified_phy=False)


def run(out):
    i,pi=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial tapped component campaign')
        (out/'state.json').write_text('{"status":"qualifying","qualified_phy":false}\n');rows=[]
        for profile,design in i['designs'].items():
            folder=out/profile;folder.mkdir();g=design['graph'];plan=design['plan'];name=g['top']
            placed=assembly.opendb(folder,dict(pi,_parent=i['library']),g,plan)
            file=assembly.gds(folder,ROOT/i['library'],g,plan)
            geometry=assembly.drc(folder,file,name)
            if geometry['drc_count']!='0':raise ValueError('Tapped output placement DRC failed')
            physical,params=qualify(folder,file,g,plan,design['reference'])
            expected_count=20*cells.COPIES[profile]
            if params['native_primitives']!=expected_count:raise ValueError('Tapped output physical native census changed')
            gds=ROOT/physical['gds'];digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
            namespace=ROOT/'build/extracted'/digest[:16]/name
            if namespace.exists():raise ValueError('Retain existing or partial tapped component extraction')
            ports={n:dict(x_um=(p['rect'][0]+p['rect'][2])/2,y_um=(p['rect'][1]+p['rect'][3])/2) for n,p in plan['ports'].items()}
            info=extractor.extract(name,gds,sha(out/'manifest.json'),ports=ports,source_scope=sha(folder/'native'/(name+'.sch.spice')))
            if info['ports']!=g['ports'] or not info['ports_verified']:raise ValueError('Tapped output RC public port order changed')
            proof=certify(folder,info,name,folder/'native'/(name+'.lvs.spice'),expected_count)
            rows.append(dict(profile=profile,graph=g,plan=plan,placement=placed,placement_geometry=geometry,
                physical=physical,native_parameters=params,extraction=info,rc_proof=proof))
        bound(out)
        report=dict(rows=rows,parallel_coarse_components_passed=True,added_cell_junctions_and_component_rc_qualified=True,
            complete_bank_interconnect_qualified=False,electrical_qualification_passed=False,qualified_phy=False)
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        report['extracted_files']={str(p.relative_to(ROOT)):sha(p) for row in rows for p in [ROOT/row['extraction']['raw_netlist'],ROOT/row['extraction']['netlist']]}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
