#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route the repaired counter and both native clock drivers as one physical block.

Real M3 spines and M4 local escapes meet per-stage M5 buses. Native component
GDS and source remain intact. Full-block DRC/LVS does not admit timing or PHY.
"""
import argparse
from collections import defaultdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import layout
import build_compound_drivers_v3 as native
import probe_static_phase_clock_release_v6 as candidate
import restrict_macro_rails_v6 as access
import build_static_phase_backend_v3 as baseline
import probe_counter_native_repairs_v183 as repaired
import native_clock_components_v2 as components

ROOT=candidate.ROOT
NAME='openlvds_repaired_clock_counter_v191'
VERSION='repaired-native-counter-and-two-clock-drivers-physical-v191.1'
CONTEXT='repaired_clock_counter_physical_v191'
sha=candidate.sha
PORTS=candidate.HPORTS
SCOPE='Actual repaired 19-macro counter plus two native clock buffers and shared supply/clock/control wiring; physical DRC/LVS only, no new RC/timing/all-PVT/full-clock/PHY admission'


def default_plan():
    return dict(setter_x_um=25.,first_row_y_um=10.,row_pitch_um=40.,corridor_um=24.,
                signal_width_um=.3,spine_width_um=.4,power_width_um=.6,power_spine_width_um=2.,
                via_cut_um=.32,via_pad_um=.4,bus_width_um=1.6,bus_pitch_um=4.,
                via4_cut_um=1.8,via4_pad_um=2.2)


def macro(name,folder,row):
    if not row['passed'] or row['drc_count']!='0' or not row['lvs_passed']:raise ValueError('Require passing native macro geometry')
    gds=folder/(name+'.gds');lef=folder/(name+'.lef');sch=folder/(name+'.sch.spice')
    if sha(gds)!=row['gds_sha256'] or sha(lef)!=row['lef_sha256'] or sha(sch)!=row['lvs_source_sha256']:raise ValueError('Native physical macro changed')
    text=lef.read_text();geom=native.lef_cell(text,name);origin=re.search(r'\bORIGIN\s+([-0-9.]+)\s+([-0-9.]+)',text)
    if not origin:raise ValueError('Missing physical macro origin')
    ox,oy=map(float,origin.groups())
    return dict(folder=str(folder.relative_to(ROOT)),row=row,bbox=[-ox,-oy,geom['width']-ox,geom['height']-oy],width=geom['width'],lef=geom)


def expected_cells(module,cells_text):
    defs=components.definitions(cells_text+module);result=[]
    counter='openlvds_routed_pair_static_phase_release_v2';harness='openlvds_static_phase_release_loaded_v2'
    for w in defs[counter][1]+[w for w in defs[harness][1] if w[0] in ('Xclock_driver','Xclock_driver_parallel')]:
        if w[0][0]!='X' or w[-1] not in defs:raise ValueError('Unexpected repaired counter macro')
        ports=defs[w[-1]][0]
        if len(w[1:-1])!=len(ports):raise ValueError('Repaired macro interface changed')
        result.append(dict(name=w[0][1:],model=w[-1],pins=dict(zip(ports,w[1:-1]))))
    if len(result)!=21 or len({r['name'] for r in result})!=21:raise ValueError('Require 19 counter and two clock macros')
    return result


def materials(parent):
    m=repaired.bound(parent);i=m['identity'];report=json.loads((parent/'summary.json').read_text())
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=6,errors=0,qualified_phy=False) or len(report['rows'])!=6:raise ValueError('Require complete repaired counter pilot')
    for row in report['rows']:
        d=row['result'] or {}
        if row['error'] is not None or not all(d.get(k) is True for k in ('hypothesis_point_checks_passed','storage_component_physical_rc_qualified','setter_guard_geometry_qualified')):raise ValueError('Repaired component or pilot failed')
    # Find the exact original physical families through the pilot's frozen lineage.
    originals=[ROOT/n for n in i['inputs'] if re.fullmatch(r'build/diagnostics/static_phase_clock_release_v6/[0-9a-f]{16}/manifest.json',n)]
    if len(originals)!=1:raise ValueError('Require unique original static counter family ancestry')
    _,_,old_cells,macros,files=baseline.materials(originals[0].parent)
    setter=repaired.evidence(ROOT/i['component']);si=setter['identity'];storage=repaired.source.evidence(ROOT/json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity']['component'])
    sr=storage['report'];storage_folder=ROOT/Path(sr['physical']['gds']).parent
    storage_name=repaired.source.NEW
    row=dict(sr['physical'],ports=storage['identity']['anchors'],macro=storage_name,
             gds_sha256=sr['extraction']['gds_sha256'],lef_sha256=sha(storage_folder/(storage_name+'.lef')))
    macros[storage_name]=macro(storage_name,storage_folder,row)
    pair_parent=ROOT/si['parent'];pair_report=json.loads((pair_parent/'summary.json').read_text());pair_rows=[r for r in pair_report['rows'] if r['macro']==repaired.NEW]
    if len(pair_rows)!=1:raise ValueError('Missing actual repaired setter pair')
    macros[repaired.NEW]=macro(repaired.NEW,pair_parent/repaired.NEW,pair_rows[0])
    cells=expected_cells((parent/'pair.spice').read_text(),(parent/'cells.spice').read_text())
    old={r['name']:r for r in old_cells};new={r['name']:r for r in cells}
    for tag,cell in old.items():
        expected=dict(cell,model=storage_name if tag=='low0_q' else repaired.NEW if tag=='low0_set_pair' else cell['model'])
        if new.get(tag)!=expected:raise ValueError('Unexpected counter connectivity or component substitution')
    for tag in ('clock_driver','clock_driver_parallel'):
        if new[tag]!=dict(name=tag,model=components.CLOCK_BUFFER,pins=dict(A='RCLK',X='CLK',VGND='VGND',VPWR='VPWR')):raise ValueError('Clock driver topology changed')
    macros={name:macros[name] for name in sorted({r['model'] for r in cells})}
    files += [parent/n for n in ('manifest.json','summary.json','state.json','cells.spice','pair.spice')]+[ROOT/n for n in i['inputs']]
    files += [ROOT/n for n in {*setter['files'],*storage['files']}]
    for row in report['rows']:
        folder=parent/row['task']['id']
        if row!=json.loads((folder/'summary.json').read_text()) or any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Complete repaired pilot trace changed')
        files += [folder/'summary.json',*[folder/n for n in row['files']]]
    for model,mat in macros.items():files += [ROOT/mat['folder']/(model+suffix) for suffix in ('.gds','.mag','.lef','.sch.spice','.lvs.log','.drc_count.txt')]
    return m,cells,macros,files


def placement(cells,macros,plan):
    stage_names=[s[0] for s in candidate.circuit.previous.previous.STAGES]
    setters=[c for c in cells if '_set' in c['name']];qs=[c for c in cells if c['name'].endswith('_q')]
    x0=plan['setter_x_um'];qx=x0+max(macros[c['model']]['bbox'][2] for c in setters)+plan['corridor_um']
    bx=qx+max(macros[c['model']]['bbox'][2] for c in qs)+plan['corridor_um'];places={}
    for cell in cells:
        n=cell['name']
        if n=='request_driver':x=qx;y=plan['first_row_y_um']+6*plan['row_pitch_um']+4
        elif n in ('clock_driver','clock_driver_parallel'):x=qx if n=='clock_driver' else bx;y=plan['first_row_y_um']+7*plan['row_pitch_um']+4
        else:
            stages=[s for s in stage_names if n.startswith(s+'_')]
            if len(stages)!=1:raise ValueError('Unknown counter placement role')
            y=plan['first_row_y_um']+stage_names.index(stages[0])*plan['row_pitch_um']
            x=x0 if '_set' in n else qx if n.endswith('_q') else bx
        places[n]=dict(x=x,y=y)
    return places,qx,bx


def routing(cells,places,qx,bx,plan):
    points=defaultdict(list);buses={};intervals=[]
    for i,(tag,prior,high,out) in enumerate(candidate.circuit.previous.previous.STAGES):
        y=plan['first_row_y_um']+i*plan['row_pitch_um']
        buses.update({out:y+22,tag+'_sn':y+26,tag+'_qb':y+30})
    top=plan['first_row_y_um']+8*plan['row_pitch_um']+26
    buses.update(request_i=top,REQUEST=top+plan['bus_pitch_um'],CLK=top+2*plan['bus_pitch_um'],VGND=top+3*plan['bus_pitch_um'],VPWR=top+4*plan['bus_pitch_um'],RCLK=top+5*plan['bus_pitch_um'])
    for cell in cells:
        n=cell['name'];x=places[n]['x'];y=places[n]['y']
        for pin,net in cell['pins'].items():
            if pin=='VGND':track=x-11
            elif pin=='VPWR':track=x-8
            elif n in ('clock_driver','clock_driver_parallel'):track=8. if pin=='A' else 5.
            elif n=='request_driver':track=qx-20 if pin=='A' else qx-14
            elif '_set' in n:track=5. if net=='CLK' else 2. if net=='request_i' else x-14 if pin=='Y' else x-17
            elif n.endswith('_q'):track=qx-20 if pin=='A' else qx-17 if pin=='B' else qx-14
            else:track=bx-20 if pin=='A' else bx-17 if pin=='B' else bx-14
            if net not in buses:raise ValueError('Unrouted counter net '+net)
            points[net].append(dict(cell=n,pin=pin,x=track))
    if set(points)!=set(buses):raise ValueError('Missing counter bus coverage')
    return dict(points),buses


def source(cells,macros):
    blocks={};order=[]
    for name,macro in sorted(macros.items()):
        text=(ROOT/macro['folder']/(name+'.sch.spice')).read_text()
        for block in re.findall(r'(?ims)^\.subckt\s+[^\n]+\n.*?^\.ends[^\n]*',text):
            model=block.split()[1];tokens=[line.split() for line in block.splitlines()]
            if model in blocks and blocks[model][0]!=tokens:raise ValueError('Conflicting native source hierarchy '+model)
            if model not in blocks:blocks[model]=(tokens,block);order.append(model)
    rows=[blocks[n][1] for n in order]+['.subckt '+NAME+' '+' '.join(PORTS)]
    for cell in cells:
        name=cell['model'];ports=blocks[name][0][0][2:]
        if set(ports)!=set(cell['pins']):raise ValueError('Physical source pin mismatch')
        rows.append('X'+cell['name']+' '+' '.join(cell['pins'][p] for p in ports)+' '+name)
    return '\n'.join(rows+['.ends '+NAME,''])



def native_master_witness(macros,output=None,cells=None,places=None):
    paths=[str(ROOT/m['folder']/(name+'.gds')) for name,m in sorted(macros.items())]
    code="""import sys,json
from collections import Counter
import klayout.db as db
paths=json.loads(sys.argv[1]);reference={};duplicates=0
for path in paths:
    layout=db.Layout();layout.read(path)
    if layout.dbu!=.001:raise ValueError('Native GDS scale changed')
    for cell in layout.each_cell():
        layers={(layout.get_info(i).layer,layout.get_info(i).datatype):db.Region(cell.shapes(i)).merged() for i in layout.layer_indexes() if not cell.shapes(i).is_empty()}
        places=Counter((layout.cell(i.cell_index).name,i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb) for i in cell.each_inst())
        if cell.name in reference:
            duplicates+=1;old,prior=reference[cell.name]
            if places!=prior or set(layers)!=set(old) or any(not (layers[k]^old[k]).is_empty() for k in layers):raise ValueError('Conflicting physical master '+cell.name)
        else:reference[cell.name]=(layers,places)
if len(sys.argv)>2:
    layout=db.Layout();layout.read(sys.argv[2])
    if layout.dbu!=.001:raise ValueError('Output GDS scale changed')
    for name,(expected,places) in reference.items():
        cell=layout.cell(name)
        if cell is None:raise ValueError('Missing native output master '+name)
        layers={(layout.get_info(i).layer,layout.get_info(i).datatype):db.Region(cell.shapes(i)).merged() for i in layout.layer_indexes() if not cell.shapes(i).is_empty()}
        actual=Counter((layout.cell(i.cell_index).name,i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb) for i in cell.each_inst())
        if places!=actual or set(layers)!=set(expected) or any(not (layers[k]^expected[k]).is_empty() for k in layers):raise ValueError('Changed integrated native master '+name)
    payload=json.loads(sys.argv[3]);top=layout.cell(payload['top'])
    if top is None:raise ValueError('Missing declared integrated top')
    expected=Counter((c['model'],db.ICplxTrans(1,0,False,round(payload['placements'][c['name']]['x']/layout.dbu),round(payload['placements'][c['name']]['y']/layout.dbu)).to_s(),0,0,0,0,0,0) for c in payload['cells'])
    actual=Counter((layout.cell(i.cell_index).name,i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb) for i in top.each_inst())
    if actual!=expected:raise ValueError('Integrated native macro placement changed')
print(json.dumps(dict(native_master_count=len(reference),identical_duplicate_masters=duplicates,all_shared_native_masters_identical=True,all_integrated_native_masters_preserved=len(sys.argv)>2,integrated_macro_placements_verified=len(sys.argv)>2)))
"""
    args=[repaired.CAD,'-c',code,json.dumps(paths)]
    if output is not None:
        if cells is None or places is None:raise ValueError('Require explicit integrated native placements')
        args += [str(output),json.dumps(dict(top=NAME,cells=cells,placements=places))]
    result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
    if result.returncode:raise ValueError('Native physical master compatibility refused:\n'+result.stderr[-2500:])
    return json.loads(result.stdout)


def prepare(parent,plan):
    m,cells,macros,files=materials(parent)
    if set(plan)!=set(default_plan()) or any(not isinstance(v,(int,float)) or v<=0 for v in plan.values()):raise ValueError('Invalid counter floorplan')
    places,qx,bx=placement(cells,macros,plan);points,buses=routing(cells,places,qx,bx,plan)
    # Build the schematic before binding a physical run to catch conflicting
    # library definitions without creating an incomplete physical artifact.
    source(cells,macros)
    witness=native_master_witness(macros)
    pdks=dict(m['identity']['pdk_files']);pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    for p in [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']:pdks[str(p)]=sha(p)
    code=[Path(__file__),Path(baseline.__file__),Path(repaired.__file__),Path(components.__file__),Path(candidate.__file__),Path(candidate.circuit.__file__),Path(candidate.families.__file__),Path(native.__file__),Path(layout.__file__),Path(access.__file__),Path(access.geometry.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,native_master_witness=witness,cad=dict(path=repaired.CAD,sha256=sha(Path(repaired.CAD))),parent=str(parent.relative_to(ROOT)),configuration=plan,cells=cells,macros=macros,placements=places,points=points,buses=buses,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code},pdk_files=pdks,tools=native.environment.tools())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or native.environment.tools()!=i['tools'] or sha(Path(repaired.CAD))!=i['cad']['sha256']):raise ValueError('Whole counter physical context changed')
    repaired.bound(ROOT/i['parent']);return m


def hierarchy(folder,name,seen=None):
    seen=set() if seen is None else seen
    if name in seen:return seen
    seen.add(name);path=folder/(name+'.mag')
    if not path.exists():raise ValueError('Missing native hierarchy '+str(path))
    for line in path.read_text().splitlines():
        if line.startswith('use '):hierarchy(folder,line.split()[1],seen)
    return seen


def draw(out,i):
    macros=i['macros'];cells=i['cells'];plan=i['configuration'];places=i['placements'];points=i['points'];buses=i['buses']
    for name,macro in macros.items():
        folder=ROOT/macro['folder'];names=sorted(hierarchy(folder,name));commands=['gds readonly false',f'gds read {{{folder/(name+".gds")}}}']
        for child in names:commands += [f'load {child} -silent',f'save {{{out/child}}}']
        layout.invoke_magic(out,'\n'.join(commands),'import_'+name)
    g=layout.Geometry();intervals=[];public={}
    def compact_via(x,y):
        g.pad('metal3',x,y,plan['via_pad_um']);g.pad('via3',x,y,plan['via_cut_um']);g.pad('metal4',x,y,plan['via_pad_um'])
    for net,ends in points.items():
        by=buses[net];power=net in ['VPWR','VGND']
        for end in ends:
            cell=next(c for c in cells if c['name']==end['cell']);p=macros[cell['model']]['row']['ports'][end['pin']];cx=places[cell['name']]['x'];cy=places[cell['name']]['y']
            py=cy+p['y_um'];tx=end['x'];width=plan['power_width_um'] if power else plan['signal_width_um']
            # All escapes stay below native MIM routes. M3 spines lie in the
            # empty corridors, and only the selected net receives each via.
            px=cx+p['x_um']
            if p['layer']=='metal3':
                shapes=macros[cell['model']]['lef']['pins'][end['pin']]
                rail=[r for layer,r in shapes if layer=='met3' and r[0]<=p['x_um']<=r[2] and r[1]<=p['y_um']<=r[3]]
                if len(rail)!=1:raise ValueError('Ambiguous native M3 rail')
                index=list(cell['pins']).index(end['pin']);px=cx+(p['x_um'] if power else rail[0][2]-3.-2*index)
                if not rail[0][0]+.3-layout.GRID/2<=px-cx<=rail[0][2]-.3+layout.GRID/2:raise ValueError('Invalid native M3 landing')
                if power:g.via34(px,py)
                else:compact_via(px,py)
            elif p['layer']!='metal4':raise ValueError('Unsupported native counter access')
            g.wire('metal4',px,py,tx,py,width)
            if power:g.via34(tx,py)
            else:compact_via(tx,py)
            sw=plan['power_spine_width_um'] if power else plan['spine_width_um'];g.wire('metal3',tx,py,tx,by,sw)
            intervals.append((tx,min(py,by)-sw/2,max(py,by)+sw/2,net))
        for tx in sorted({p['x'] for p in ends}):
            g.via34(tx,by);g.pad('metal4',tx,by,plan['via4_pad_um']);g.pad('via4',tx,by,plan['via4_cut_um']);g.pad('metal5',tx,by,plan['via4_pad_um'])
        xs=[p['x'] for p in ends];left=.3 if net in PORTS else min(xs)-1.4;right=max(xs)+1.4;bw=2. if power else plan['bus_width_um']
        g.wire('metal5',left,by,right,by,bw)
        if net in PORTS:public[net]=dict(layer='metal5',x_um=left,y_um=by,width_um=bw)
    for n,(x,a,b,net) in enumerate(intervals):
        for x2,c,d,other in intervals[n+1:]:
            if x==x2 and net!=other and max(a,c)<=min(b,d):raise ValueError('Different counter nets share a spine interval')
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rects]]
    for cell in cells:
        p=places[cell['name']];bbox=macros[cell['model']]['bbox']
        lines += [f'use {cell["model"]} {cell["name"]}','timestamp 0',f'transform 1 0 {round(p["x"]/layout.GRID)} 0 1 {round(p["y"]/layout.GRID)}',
                  'box '+' '.join(str(round(v/layout.GRID)) for v in bbox)]
    lines.append('<< labels >>')
    for index,pin in enumerate(PORTS,1):
        p=public[pin];x=round(p['x_um']/layout.GRID);y=round(p['y_um']/layout.GRID)
        lines += [f'rlabel metal5 {x} {y} {x} {y} 0 {pin}',f'port {index} nsew']
    for net,by in buses.items():
        if net in PORTS:continue
        x=round((min(p['x'] for p in points[net])-1.4)/layout.GRID);y=round(by/layout.GRID)
        lines.append(f'rlabel metal5 {x} {y} {x} {y} 0 {net}')
    lines.append('<< end >>');(out/(NAME+'.mag')).write_text('\n'.join(lines)+'\n');(out/(NAME+'.sch.spice')).write_text(source(cells,macros))
    result=layout.qualify(out,NAME);raw=out/(NAME+'.raw.lef');raw.write_bytes((out/(NAME+'.lef')).read_bytes())
    types={p:('OUTPUT' if p in ['PREPARE','RESET_N','CLK'] else 'INPUT','SIGNAL') for p in PORTS if p not in ['VPWR','VGND']};types.update(VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
    text,pins=access.restrict(raw.read_text(),public,types);(out/(NAME+'.lef')).write_text(text)
    masks=native_master_witness(macros,out/(NAME+'.gds'),cells,places)
    return dict(result,native_master_witness=masks,macro=NAME,ports=public,integration_pins=pins,macro_count=len(cells),native_macro_types=len(macros),
                gds_sha256=sha(out/(NAME+'.gds')),lef_sha256=sha(out/(NAME+'.lef')),qualified_phy=False,electrical_qualification_passed=False)


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior whole counter route')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n');folder=out/NAME;folder.mkdir()
        try:row=draw(folder,m['identity'])
        except Exception as e:
            error=dict(status='physical_exception',error=str(e),qualified_phy=False)
            (out/'execution_error.json').write_text(json.dumps(error,indent=2)+'\n')
            (out/'state.json').write_text(json.dumps(error)+'\n');raise
        (folder/'summary.json').write_text(json.dumps(row,indent=2)+'\n');bound(out)
        report=dict(rows=[row],passed=row['passed'],qualified_phy=False,electrical_qualification_passed=False,
                    scope=SCOPE)
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=report['passed'],qualified_phy=False))+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--plan',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out,json.loads(a.plan.read_text()) if a.plan else default_plan());print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
