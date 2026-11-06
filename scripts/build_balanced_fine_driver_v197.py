#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route native regular-P/N fine drivers with explicit source/drain/body straps."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import inspect_balanced_driver_pcells_v195 as primitive
import layout
import native_bank_inventory_v51 as inventory
import restrict_macro_rails_v6 as access

ROOT=primitive.ROOT
VERSION='compact-balanced-native-pn-fine-driver-actual-mim-access-v197.1'
CONTEXT='balanced_fine_driver_physical_v197'
PORTS=['A','Y','VGND','VPWR']
PROFILES=[dict(p_fingers=p,n_fingers=n) for p,n in ((20,10),(24,12))]
CAP='sky130_fd_pr__cap_mim_m3_1'
SCOPE='New native regular-P/N inverter geometry with explicit finger drain/source/bulk straps and one 2um output MIM; DRC/LVS only, no local RC/bank timing/all-PVT/PHY admission'
sha=primitive.environment.sha
atomic=primitive.atomic


def name(s):return 'openlvds_balanced_p'+str(s['p_fingers'])+'n'+str(s['n_fingers'])+'_v197'


def schematic(s):
    rows=['.subckt '+name(s)+' '+' '.join(PORTS)]
    for kind,count,w,supply in [('n',s['n_fingers'],.65,'VGND'),('p',s['p_fingers'],1.,'VPWR')]:
        rows += [f'X{kind}{k} Y A {supply} {supply} sky130_fd_pr__{kind}fet_01v8 w={w} l=.15' for k in range(count)]
    return '\n'.join(rows+['XC Y VGND '+CAP+' w=2 l=2','.ends '+name(s),''])


def materials(parent):
    m=primitive.bound(parent);report=json.loads((parent/'summary.json').read_text())
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False) or len(report['rows'])!=4:raise ValueError('Require complete native finger geometry inspection')
    files=[parent/n for n in ('manifest.json','summary.json','state.json')];rows={}
    for r in report['rows']:
        e=r['extracted'];s=r['spec'];folder=parent/r['top']
        if not r['primitive_inspection_passed'] or r['drc_count']!='0' or not all(e[k] for k in ('finger_count_and_dimensions_match','all_gates_on_named_gate','all_bodies_on_named_bulk')):raise ValueError('Native finger count/geometry/gate/bulk witness failed')
        if any(sha(folder/n)!=h for n,h in r['files'].items()):raise ValueError('Native primitive inputs changed')
        terminals=r['terminal_accesses']
        if not all(any(t['name'].startswith(k) for t in terminals) for k in ('D','S','G','B')):raise ValueError('Missing native terminal access')
        rows[s['kind'],s['fingers']]=r;files += [folder/'summary.json',*[folder/n for n in r['files']]]
    return m,rows,files


def prepare(parent):
    m,rows,files=materials(parent);files += [ROOT/n for n in m['identity']['inputs']]
    files += [Path(__file__),Path(access.__file__),Path(access.geometry.__file__),Path(inventory.__file__)]
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profiles=PROFILES,primitives=rows_to_list(rows),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in files},external_files=m['identity']['external_files'],tools=primitive.environment.tools(),scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=i,qualified_phy=False));return out


def rows_to_list(rows):return [rows[k] for k in sorted(rows)]


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['profiles']!=PROFILES
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items()) or primitive.environment.tools()!=i['tools']):raise ValueError('Balanced native driver physical context changed')
    return m


def straps(s,rows,cap):
    g=layout.Geometry();width=max(rows[k]['geometry']['bbox'][2]-rows[k]['geometry']['bbox'][0] for k in rows);cx=4+width/2
    right=cx+width/2;yx=right+2.;gx=right+3.;capx=right+4-cap['bbox'][0];capy=17.4-cap['bbox'][1]
    placed={};gate_buses=[];drain_buses=[];source_buses=[]
    for kind,cy,supply in [('n',5.,'VGND'),('p',13.,'VPWR')]:
        row=rows[kind];terminals=row['terminal_accesses'];placed[kind]=dict(x=cx,y=cy)
        def point(t):return cx+t['x_um'],cy+t['y_um']
        drains=[t for t in terminals if t['name'].startswith('D')];sources=[t for t in terminals if t['name'].startswith('S')];gates=[t for t in terminals if t['name']=='G'];bulks=[t for t in terminals if t['name']=='B']
        for ts,delta,bus in [(drains,-.25,cy-2.2),(sources,-1.25,cy-3.7)]:
            for t in ts:
                x,y=point(t);landing=y+delta
                # The primitive already has full M1/VIALI access. Stagger D/S
                # via1 landings to retain the native 0.48um contact pitch.
                g.wire('metal1',x,y,x,landing,.18);g.via12(x,landing);g.wire('metal2',x,landing,x,bus,.28);g.via23(x,bus)
        db=cy-2.2;sb=cy-3.7;gb=cy+2.4
        g.wire('metal3',.8,db,yx,db,.6);g.via34(yx,db);drain_buses.append(db)
        g.wire('metal3',.8,sb,gx if kind=='n' else right+.6,sb,.8);source_buses.append((supply,sb))
        # Body-to-source ties use M1 and stay below every drain landing.
        for t in bulks:
            x,y=point(t);near=min(sources,key=lambda q:abs(q['x_um']-t['x_um']));sx,sy=point(near);sy-=1.25
            g.pad('locali',x,y,.33);g.pad('viali',x,y,.17)
            g.rect('metal1',min(x-.15,sx-.2),min(y-.15,sy-.2),max(x+.15,sx+.2),max(y+.15,sy+.2))
        # Strap every gate access with a continuous M1 bar; do not rely on a
        # long poly connection to distribute the fast input edge.
        gate_y=max(point(t)[1] for t in gates)+.3
        for t in gates:
            x,y=point(t);g.wire('metal1',x,y,x,gate_y,.18)
        xs=[point(t)[0] for t in gates];g.wire('metal1',min(xs),gate_y,max(xs),gate_y,.4)
        x=min(xs);g.via12(x,gate_y);g.wire('metal2',x,gate_y,x,gb,.28);g.via23(x,gb)
        g.wire('metal3',1.8,gb,x+.6,gb,.6);g.via34(1.8,gb);gate_buses.append(gb)
    g.wire('metal4',1.8,min(gate_buses),1.8,17.8,.6);g.wire('metal4',yx,min(drain_buses),yx,17.8,.6)
    c1=cap['ports']['C1'];c2=cap['ports']['C2']
    if c1[0]!='mimcapcontact' or c2[0]!='via3':raise ValueError('Unexpected native MIM access layers')
    # Native C1 is a MIM-top contact with M4 access; C2 is a via3 contact.
    # Escape vertically on opposite sides. A horizontal M4 C1 escape at the
    # contact height would cross the C2 via and short the capacitor plates.
    x,y=capx+c1[1],capy+c1[2];g.wire('metal4',x,y,x,15.4,.6);g.via34(x,15.4)
    g.wire('metal3',yx,15.4,x,15.4,.6);g.via34(yx,15.4)
    x,y=capx+c2[1],capy+c2[2];g.wire('metal3',x,14.4,x,y,.6);g.wire('metal3',gx,14.4,x,14.4,.6)
    g.via23(gx,14.4);g.wire('metal2',gx,1.3,gx,14.4,.4);g.via23(gx,1.3)
    placed['cap']=dict(x=capx,y=capy)
    ports=dict(A=dict(layer='metal4',x_um=1.8,y_um=17.8,width_um=.6),Y=dict(layer='metal4',x_um=yx,y_um=17.8,width_um=.6),
               VGND=dict(layer='metal3',x_um=.8,y_um=1.3,width_um=.8),VPWR=dict(layer='metal3',x_um=.8,y_um=9.3,width_um=.8))
    return g,placed,ports


def draw(folder,parent,s,rows):
    for r in rows.values():shutil.copyfile(parent/r['top']/(r['top']+'.mag'),folder/(r['top']+'.mag'))
    capname='balanced_guard2_v197';layout.invoke_magic(folder,f'''load {capname} -silent
box values 0 0 0 0
set p [sky130::sky130_fd_pr__cap_mim_m3_1_defaults]
dict set p w 2
dict set p l 2
sky130::sky130_fd_pr__cap_mim_m3_1_draw $p
save {capname}
''','guard_pcell')
    cap=layout.pcell_info(folder/(capname+'.mag'));g,places,ports=straps(s,rows,cap);lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rectangles in g.layers.items():lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rectangles]]
    for key,model,bbox in [(k,rows[k]['top'],rows[k]['geometry']['bbox']) for k in ('n','p')]+[('cap',capname,cap['bbox'])]:
        p=places[key];lines += [f'use {model} {key}','timestamp 0',f'transform 1 0 {round(p["x"]/layout.GRID)} 0 1 {round(p["y"]/layout.GRID)}','box '+' '.join(str(round(v/layout.GRID)) for v in bbox)]
    lines.append('<< labels >>')
    for k,pin in enumerate(PORTS,1):
        p=ports[pin];x=round(p['x_um']/layout.GRID);y=round(p['y_um']/layout.GRID);lines += [f'rlabel {p["layer"]} {x} {y} {x} {y} 0 {pin}',f'port {k} nsew']
    lines.append('<< end >>');top=name(s);(folder/(top+'.mag')).write_text('\n'.join(lines)+'\n');(folder/(top+'.sch.spice')).write_text(schematic(s))
    physical=layout.qualify(folder,top);raw=folder/(top+'.raw.lef');raw.write_bytes((folder/(top+'.lef')).read_bytes())
    types=dict(A=('INPUT','SIGNAL'),Y=('OUTPUT','SIGNAL'),VGND=('INOUT','GROUND'),VPWR=('INOUT','POWER'))
    lef,pins=access.restrict(raw.read_text(),ports,types);(folder/(top+'.lef')).write_text(lef)
    _,devices=inventory.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',(folder/(top+'.lvs.spice')).read_text()),top+'_flat')
    _,expected=inventory.native_leaves(schematic(s),top)
    parameters=inventory.compare_parameters(expected,devices)
    counts={model:sum(d['model']==model for d in devices) for model in ('sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8',CAP)}
    correct=counts=={'sky130_fd_pr__nfet_01v8':s['n_fingers'],'sky130_fd_pr__pfet_01v8':s['p_fingers'],CAP:1}
    return dict(physical,macro=top,spec=s,ports=ports,integration_pins=pins,placements=places,native_model_counts=counts,native_parameters=parameters,native_inventory_passed=correct,
                passed=physical['passed'] and correct,gds_sha256=sha(folder/(top+'.gds')),lef_sha256=sha(folder/(top+'.lef')),local_rc_qualified=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity'];parent=ROOT/i['parent'];by={(r['spec']['kind'],r['spec']['fingers']):r for r in i['primitives']}
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial balanced driver layout')
        atomic(out/'state.json',dict(status='routing',qualified_phy=False));rows=[]
        try:
            for s in PROFILES:
                folder=out/name(s);folder.mkdir();r=draw(folder,parent,s,{k:by[k,s[k+'_fingers']] for k in ('n','p')});r['files']={p.name:sha(p) for p in folder.iterdir() if p.is_file()};atomic(folder/'summary.json',r);rows.append(r)
            bound(out);passed=all(r['passed'] for r in rows);atomic(out/'summary.json',dict(rows=rows,passed=passed,scope=SCOPE,qualified_phy=False));atomic(out/'state.json',dict(status='complete',passed=passed,qualified_phy=False));return out
        except Exception as e:atomic(out/'state.json',dict(status='failed',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
