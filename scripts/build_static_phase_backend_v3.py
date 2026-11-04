#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route the full 19-macro static phase counter from its exact native topology.

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
import layout
import build_compound_drivers_v3 as native
import probe_static_phase_clock_release_v6 as candidate
import restrict_macro_rails_v6 as access

ROOT=candidate.ROOT
NAME='openlvds_static_phase_backend_v2'
VERSION='whole-native-static-phase-counter-physical-v2.2'
CONTEXT='static_phase_backend_physical_v2'
sha=candidate.sha
PORTS=candidate.circuit.PORTS


def default_plan():
    return dict(setter_x_um=25.,first_row_y_um=10.,row_pitch_um=40.,corridor_um=24.,
                signal_width_um=.3,spine_width_um=.4,power_width_um=.6,
                via_cut_um=.32,via_pad_um=.4,bus_width_um=1.6,bus_pitch_um=4.,
                via4_cut_um=1.8,via4_pad_um=2.2)


def instances(rc):
    text=candidate.circuit.source(rc,'pair');result=[]
    for row in text.splitlines()[1:-1]:
        w=row.split()
        if len(w)<3 or not w[0].startswith('X') or w[-1] not in rc:raise ValueError('Unexpected native counter statement')
        ports=rc[w[-1]]['info']['ports']
        if len(w[1:-1])!=len(ports):raise ValueError('Counter child interface mismatch')
        result.append(dict(name=w[0][1:],model=w[-1],pins=dict(zip(ports,w[1:-1]))))
    if len(result)!=19 or len({c['name'] for c in result})!=19:raise ValueError('Require all 19 native counter macros')
    return result


def materials(parent):
    m=candidate.bound(parent);rc={};files=[parent/'manifest.json'];files += [ROOT/n for n in m['identity']['inputs']]
    for p in m['identity']['families']:
        group,paths=candidate.families.witnesses(ROOT/p)
        if set(group)&set(rc):raise ValueError('Duplicate native model')
        rc.update(group);files+=paths
    cells=instances(rc);macros={}
    for name in sorted({c['model'] for c in cells}):
        info=rc[name]['info'];gds={p for p in files if p.name==name+'.gds' and sha(p)==info['gds_sha256']}
        if len(gds)!=1:raise ValueError('Require unique exact physical view for '+name)
        gds=next(iter(gds));folder=gds.parent;row=json.loads((folder/'summary.json').read_text())
        if (not row['passed'] or row['drc_count']!='0' or not row['lvs_passed']
            or sha(folder/(name+'.lef'))!=row['lef_sha256']
            or sha(folder/(name+'.sch.spice'))!=info['source_scope_sha256']):raise ValueError('Native macro physical proof changed')
        lef=(folder/(name+'.lef')).read_text();geom=native.lef_cell(lef,name);origin=re.search(r'\bORIGIN\s+([-0-9.]+)\s+([-0-9.]+)',lef)
        if not origin:raise ValueError('Missing native macro origin')
        ox,oy=map(float,origin.groups());bbox=[-ox,-oy,geom['width']-ox,geom['height']-oy]
        macros[name]=dict(folder=str(folder.relative_to(ROOT)),row=row,bbox=bbox,width=geom['width'],lef=geom)
        files += [folder/(name+n) for n in ['.gds','.lef','.sch.spice','.lvs.log','.drc_count.txt']]+[folder/'summary.json']
    return m,rc,cells,macros,files


def placement(cells,macros,plan):
    stage_names=[s[0] for s in candidate.circuit.previous.previous.STAGES]
    setters=[c for c in cells if '_set' in c['name']];qs=[c for c in cells if c['name'].endswith('_q')]
    x0=plan['setter_x_um'];qx=x0+max(macros[c['model']]['bbox'][2] for c in setters)+plan['corridor_um']
    bx=qx+max(macros[c['model']]['bbox'][2] for c in qs)+plan['corridor_um'];places={}
    for cell in cells:
        n=cell['name']
        if n=='request_driver':x=qx;y=plan['first_row_y_um']+6*plan['row_pitch_um']+4
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
    top=plan['first_row_y_um']+6*plan['row_pitch_um']+26
    buses.update(request_i=top,REQUEST=top+plan['bus_pitch_um'],CLK=top+2*plan['bus_pitch_um'],VGND=top+3*plan['bus_pitch_um'],VPWR=top+4*plan['bus_pitch_um'])
    for cell in cells:
        n=cell['name'];x=places[n]['x'];y=places[n]['y']
        for pin,net in cell['pins'].items():
            if pin=='VGND':track=x-11
            elif pin=='VPWR':track=x-8
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


def prepare(parent,plan):
    m,rc,cells,macros,files=materials(parent)
    if set(plan)!=set(default_plan()) or any(not isinstance(v,(int,float)) or v<=0 for v in plan.values()):raise ValueError('Invalid counter floorplan')
    places,qx,bx=placement(cells,macros,plan);points,buses=routing(cells,places,qx,bx,plan)
    # Build the schematic before binding a physical run to catch conflicting
    # library definitions without creating an incomplete physical artifact.
    source(cells,macros)
    pdks=dict(m['identity']['pdk_files']);pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    for p in [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']:pdks[str(p)]=sha(p)
    code=[Path(__file__),Path(candidate.__file__),Path(candidate.circuit.__file__),Path(candidate.families.__file__),Path(native.__file__),Path(layout.__file__),Path(access.__file__),Path(access.geometry.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),configuration=plan,cells=cells,macros=macros,placements=places,points=points,buses=buses,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code},pdk_files=pdks,tools=native.environment.tools())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or native.environment.tools()!=i['tools']):raise ValueError('Whole counter physical context changed')
    candidate.bound(ROOT/i['parent']);return m


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
            sw=plan['power_width_um'] if power else plan['spine_width_um'];g.wire('metal3',tx,py,tx,by,sw)
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
    lines.append('<< end >>');(out/(NAME+'.mag')).write_text('\n'.join(lines)+'\n');(out/(NAME+'.sch.spice')).write_text(source(cells,macros))
    result=layout.qualify(out,NAME);raw=out/(NAME+'.raw.lef');raw.write_bytes((out/(NAME+'.lef')).read_bytes())
    types={p:('OUTPUT' if p in ['PREPARE','RESET_N'] else 'INPUT','SIGNAL') for p in PORTS if p not in ['VPWR','VGND']};types.update(VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
    text,pins=access.restrict(raw.read_text(),public,types);(out/(NAME+'.lef')).write_text(text)
    return dict(result,macro=NAME,ports=public,integration_pins=pins,macro_count=len(cells),native_macro_types=len(macros),
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
                    scope='Whole 19-native-macro static phase counter route/DRC/LVS; no whole-block RC timing, full-PVT or PHY admission')
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=report['passed'],qualified_phy=False))+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--plan',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out,json.loads(a.plan.read_text()) if a.plan else default_plan());print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
