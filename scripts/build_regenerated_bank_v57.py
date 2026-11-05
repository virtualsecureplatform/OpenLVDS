#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route branch-regenerated bank and qualify actual GDS; no timing transfer."""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import klayout.db as db
import regenerated_bank_physical_v57 as design
import build_tg_bank_floorplan_v49 as assembly
import probe_tg_bank_route_v50 as routing
import build_tg_bank_gds_v51 as streamout

ROOT=assembly.ROOT
sha=assembly.sha
VERSION='regenerated-159-cell-tapped-bank-actual-routing-native-gds-v57.1'
CONTEXT='regenerated_bank_physical_v57'


def candidate(parent):
    code='import sys,json;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/"scripts"));import probe_regenerated_bank_v56 as p;m=p.bound(Path(sys.argv[2]));print(json.dumps(m,sort_keys=True))'
    p=subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(ROOT),str(parent)],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


def inputs(parent,registry):
    c=candidate(parent);ai=assembly.audit.bound(registry);lib=ROOT/ai['parent'];pi=assembly.audit.producer.bound(lib)
    r=json.loads((lib/'summary.json').read_text());original=json.loads((ROOT/pi['graph_parent']/'manifest.json').read_text())['identity']['graph']
    g=design.graph(original);plan=design.placement(original,g,r['cells'])
    reference=design.native_source(g,(ROOT/pi['graph_parent']/'bank.sch.spice').read_text(),(parent/'bank.spice').read_text())
    return c,lib,pi,g,plan,reference


def route_script(parent,out,plan):
    text=routing.route_tcl(parent,out,plan)
    marker='[$block findNet IN] setSpecial\n'
    if text.count(marker)!=1:raise ValueError('Immutable routing adapter changed')
    return text.replace(marker,'# IN drives two physical cells and must be routed.\n',1)


def check_verilog(out,g,yosys):
    (out/'bank.v').write_text(design.verilog(g));(out/'cells.v').write_text(design.original.blackboxes(g))
    script='read_verilog -lib cells.v\nread_verilog bank.v\nhierarchy -check -top '+g['top']+'\nwrite_json bank.json\n'
    (out/'check.ys').write_text(script)
    p=subprocess.run([yosys,'-s','check.ys'],cwd=out,capture_output=True,text=True)
    (out/'yosys.log').write_text(p.stdout+p.stderr);p.check_returncode()
    data=json.loads((out/'bank.json').read_text());result=design.verify_json(data,g)
    bad=deepcopy(data);top=bad['modules'][g['top']]
    top['cells']['u_switch1_0_0']['connections']['A']=top['ports']['IN']['bits']
    try:design.verify_json(bad,g)
    except ValueError:pass
    else:raise ValueError('Root regeneration bypass corruption was accepted')
    return dict(result=result,wrong_root_regeneration_bypass_rejected=True)


def qualify(out,file,g,plan,reference):
    name=g['top'];folder=out/'native';folder.mkdir();(folder/(name+'.sch.spice')).write_text(reference)
    lib=db.Layout();lib.read(str(file));commands=['gds readonly false',f'gds read {{{file}}}']
    for cell in lib.each_cell():commands += [f'load {cell.name}',f'save {cell.name}']
    commands += [f'load {name}']
    for index,port in enumerate(g['ports'],1):
        x0,y0,x1,y1=plan['ports'][port]['rect'];x=(x0+x1)/2;y=(y0+y1)/2
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um',f'port make {index}']
    commands += [f'save {name}'];assembly.layout.invoke_magic(folder,'\n'.join(commands),'import_routed')
    q=assembly.layout.qualify(folder,name)
    if not q['passed']:return q,None
    _,expected=streamout.native_leaves(reference,name)
    text=re.sub(r'\n[ \t]*\+[ \t]*',' ',(folder/(name+'.lvs.spice')).read_text())
    _,actual=streamout.native_leaves(text,name+'_flat')
    params=streamout.inventory.compare_parameters(expected,actual)
    if params['native_primitives']!=1019 or params['native_model_counts'].get('sky130_fd_pr__cap_mim_m3_1')!=68:
        raise ValueError('Physical regeneration native inventory changed')
    return q,params


def prepare(parent,registry):
    c,lib,pi,g,plan,reference=inputs(parent,registry)
    paths=[parent/'manifest.json',parent/'bank.spice',*[ROOT/n for n in c['identity']['inputs']],registry/'manifest.json',registry/'summary.json']
    rr=json.loads((registry/'summary.json').read_text());paths += [registry/n for n in rr['files']]
    paths += [lib/'manifest.json',lib/'summary.json']+[lib/n for n in json.loads((lib/'summary.json').read_text())['files']]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    paths += [routing.TEMPLATE]
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/klayout/tech';external={str(p):sha(p) for p in [tech/'sky130A.lyt',tech/'sky130A.map']}
    tool=Path(shutil.which('yosys'))
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),registry=str(registry.relative_to(ROOT)),library=str(lib.relative_to(ROOT)),
                  graph=g,plan=plan,reference_sha256=hashlib.sha256(reference.encode()).hexdigest(),
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},external_files=external,
                  yosys=dict(path=str(tool),sha256=sha(tool)),lyt=str(tech/'sky130A.lyt'),mapping=str(tech/'sky130A.map'))
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'reference.spice').write_text(reference);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(Path(n))!=h for n,h in i['external_files'].items())
            or sha(Path(i['yosys']['path']))!=i['yosys']['sha256']
            or sha(out/'reference.spice')!=i['reference_sha256']):raise ValueError('Regenerated physical context changed')
    c,lib,pi,g,plan,reference=inputs(ROOT/i['parent'],ROOT/i['registry'])
    if json.loads(json.dumps(g))!=i['graph'] or json.loads(json.dumps(plan))!=i['plan']:
        raise ValueError('Regenerated physical graph/placement cannot regenerate')
    return i,pi


def run(out):
    i,pi=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial regenerated physical campaign')
        (out/'state.json').write_text('{"status":"placing","qualified_phy":false}\n')
        g=i['graph'];plan=i['plan'];lib=ROOT/i['library'];records=json.loads((lib/'summary.json').read_text())['cells']
        graph_proof=check_verilog(out,g,i['yosys']['path'])
        placed=assembly.opendb(out,dict(pi,_parent=i['library']),g,plan)
        placed_gds=assembly.gds(out,lib,g,plan)
        shutil.copyfile(placed_gds,out/'placed_source.gds')
        buses=assembly.fixed_bus_audit(placed_gds,g,plan,records)
        geometry=assembly.drc(out,placed_gds,g['top'])
        if not geometry['placement_and_fixed_bus_drc_passed']:raise ValueError('Regenerated placement/fixed-bus DRC failed')
        routes=out/'route';routes.mkdir();(routes/'route.tcl').write_text(route_script(out,routes,plan))
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n')
        p=subprocess.run([pi['openroad']['path'],'-no_init','-exit',str(routes/'route.tcl')],cwd=routes,capture_output=True,text=True)
        (routes/'openroad.log').write_text(p.stdout+p.stderr);p.check_returncode()
        nets=sorted((set(g['ports'])|{n for c in g['cells'] for n in c['pins'].values()})-{'OUT'})
        coverage=routing.check(routes,dict(graph=g,plan=plan),nets)
        violations=re.findall(r'Number of violations\s*=\s*(\d+)',p.stdout+p.stderr)
        if not violations or int(violations[-1])!=0:raise ValueError('Regenerated detailed routing has violations')
        (out/'state.json').write_text('{"status":"native_gds","qualified_phy":false}\n')
        file=streamout.stream(out,routes,dict(parent=i['library'],graph=g,plan=plan),Path(i['lyt']),Path(i['mapping']))
        # streamout writes the same top filename, so preserve the placement
        # source separately before this stage in a dedicated path.
        source=out/'placed_source.gds'
        masks=streamout.masks(file,source,g['top'],plan['die'])
        q,params=qualify(out,file,g,plan,(out/'reference.spice').read_text())
        bound(out);passed=bool(q['passed'] and params is not None)
        result=dict(graph=graph_proof,placement=placed,fixed_buses=buses,placement_geometry=geometry,routing=coverage,
                    mask_proof=masks,physical=q,native_parameters=params,native_regenerated_gds_passed=passed,
                    joint_rc_extracted=False,electrical_qualification_passed=False,qualified_phy=False,
                    component_feasibility_not_transferred=True,full_foundry_signoff_passed=False)
        result['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--registry',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.registry is None:p.error('--registry required')
        out=prepare(out,a.registry.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
