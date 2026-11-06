#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route the first repaired counter feedback directly between native gate accesses."""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import layout
import build_direct_feedback_counter_v212 as prior
import qualify_repaired_clock_counter_rc_v193 as qualified
from probe_digital_dcc_v2 import atomic

original=qualified.physical.source
ROOT=original.ROOT
# Keep the original standalone top name; each geometry has a distinct GDS hash
# and extraction namespace. No old view or receipt is overwritten.
NAME=original.NAME
PORTS=original.PORTS
VERSION='strong-native-storage-parallel-request-solid-feedback-stems-v234.1'
CONTEXT='strong_storage_counter_physical_v234'
SCOPE='Six guarded body-contact NAND8 storage cells, two native REQUEST buffers, unchanged phase logic and clock drivers, three direct low-phase feedbacks; 22-macro physical proof only, no RC/timing/all-PVT/PHY admission'
STORAGE='openlvds_nand2_8_bodytap_v229'
Q_TAGS={'low0_q','high1_q','low1_q','high2_q','low2_q','release_q'}
sha=qualified.sha
native=original.native
access=original.access
hierarchy=original.hierarchy
native_master_witness=original.native_master_witness


def strong_plan(cells,macros,configuration):
    plan=dict(configuration,row_pitch_um=32.)
    places,qx,bx=original.placement([c for c in cells if c['name']!='request_driver_parallel'],macros,plan)
    places['request_driver_parallel']=dict(x=bx,y=places['request_driver']['y'])
    # Leave four extra micrometres after the fourth bundle's raised buses.
    # Otherwise its feedback spine intersects the next row's feedback input.
    for cell in cells:
        if cell['name'].startswith(('low2_','release_')):places[cell['name']]['y']+=4
    points,buses=original.routing(cells,places,qx,bx,plan)
    for net in ('armed','low2_sn','low2_qb','RESET_N','release_sn','release_qb'):buses[net]+=4
    # Five global buses fit in the unused M5 gap between the third and fourth
    # stage bundles. Keep the ideal-source RCLK access above the final stage.
    y=plan['first_row_y_um']+3*plan['row_pitch_um']+4
    # Keep wide M4/M5 via landings clear of the stage-three B input escape.
    # Move the fourth local M5 bundle up by 4um to preserve bus spacing.
    for net in ('PREPARE','high2_sn','high2_qb'):buses[net]+=4
    for k,net in enumerate(('request_i','REQUEST','CLK','VGND','VPWR')):buses[net]=y+4*k
    buses['RCLK']=plan['first_row_y_um']+6*plan['row_pitch_um']+26
    # The original driver escapes share columns with local Q gates. That is
    # legal only above all stages. Moving their bus into the middle requires
    # dedicated columns outside the native signal corridors.
    for net,track in (('REQUEST',6.5),('request_i',2.)):
        matches=[end for end in points[net] if end['cell'] in ('request_driver','request_driver_parallel')]
        if len(matches)!=2:raise ValueError('Require two original-polarity REQUEST driver escapes')
        for end in matches:end['x']=track
    direct=[]
    for stage in ('low0','low1','low2'):
        feedback=stage+'_qb';d=feedback_accesses(cells,macros,places,stage)
        if {(e['cell'],e['pin']) for e in points[feedback]}!={(stage+'_q','B'),(stage+'_b','Y')}:raise ValueError('Unexpected native feedback fanout')
        direct.append(d);del points[feedback];del buses[feedback]
    require_spine_clearance(cells,macros,places,points,buses,plan)
    ordered=sorted(buses.items(),key=lambda kv:kv[1])
    if any(b-a<4-1e-9 for (_,a),(_,b) in zip(ordered,ordered[1:])):raise ValueError('Compact M5 bus spacing changed')
    return dict(configuration=plan,placements=places,points=points,buses=buses,direct_feedback=direct)


def feedback_accesses(cells,macros,places,stage):
    lookup={c['name']:c for c in cells};ends=[]
    uses={(c['name'],pin) for c in cells for pin,net in c['pins'].items() if net==stage+'_qb'}
    if uses!={(stage+'_q','B'),(stage+'_b','Y')}:raise ValueError('Direct feedback requires exactly original Q.B and B.Y terminals')
    for tag,pin in ((stage+'_q','B'),(stage+'_b','Y')):
        c=lookup[tag];m=macros[c['model']];p=m['row']['ports'][pin]
        if p['layer']!='metal3':raise ValueError('Require actual native M3 feedback access')
        rails=[r for layer,r in m['lef']['pins'][pin] if layer=='met3' and r[0]<=p['x_um']<=r[2] and r[1]<=p['y_um']<=r[3]]
        if len(rails)!=1:raise ValueError('Ambiguous native M3 feedback rail')
        x=rails[0][2]-3.-2*list(c['pins']).index(pin)
        if not rails[0][0]+.3-layout.GRID/2<=x<=rails[0][2]-.3+layout.GRID/2:raise ValueError('Invalid native feedback landing')
        ends.append(dict(cell=tag,pin=pin,x_um=places[tag]['x']+x,y_um=places[tag]['y']+p['y_um']))
    if ends[0]['x_um']>=ends[1]['x_um'] or ends[0]['y_um']>=ends[1]['y_um']:raise ValueError('Unexpected native first-loop relative geometry')
    return dict(net=stage+'_qb',layer='metal4',width_um=.3,vertical_width_um=.4,ends=ends)


def require_spine_clearance(cells,macros,places,points,buses,plan):
    lookup={c['name']:c for c in cells};segments=[]
    for net,ends in points.items():
        width=plan['power_spine_width_um'] if net in ('VPWR','VGND') else plan['spine_width_um']
        for end in ends:
            cell=lookup[end['cell']];pin=macros[cell['model']]['row']['ports'][end['pin']]
            py=places[cell['name']]['y']+pin['y_um']
            segments.append((end['x'],min(py,buses[net])-width/2,max(py,buses[net])+width/2,width,net))
    for k,(x,a,b,width,net) in enumerate(segments):
        for x2,c,d,width2,other in segments[k+1:]:
            if net!=other and max(a,c)<=min(b,d) and abs(x-x2)<(width+width2)/2+.3-1e-9:
                raise ValueError('Different counter nets violate M3 spine clearance: '+net+' / '+other)


def wire_spans(cells,macros,places,points,buses):
    # Union vertical segments on each same-net spine, rather than counting
    # overlapping repeated shared-net strokes as separate physical wires.
    result={};lookup={c['name']:c for c in cells}
    for net,ends in points.items():
        groups={}
        for end in ends:
            c=lookup[end['cell']];p=macros[c['model']]['row']['ports'][end['pin']]
            py=places[c['name']]['y']+p['y_um'];groups.setdefault(end['x'],[]).append((min(py,buses[net]),max(py,buses[net])))
        length=0.
        for intervals in groups.values():
            intervals.sort();lo,hi=intervals[0]
            for a,b in intervals[1:]:
                if a<=hi:hi=max(hi,b)
                else:length+=hi-lo;lo,hi=a,b
            length+=hi-lo
        result[net]=length
    return result


def strengthened_cells(cells):
    if len(cells)!=21 or len({c['name'] for c in cells})!=21 or {c['name'] for c in cells if c['name'].endswith('_q')}!=Q_TAGS:raise ValueError('Require exact original 21-macro counter')
    result=deepcopy(cells)
    for c in result:
        if c['name'] in Q_TAGS:c['model']=STORAGE
    request=deepcopy(next(c for c in result if c['name']=='request_driver'));request['name']='request_driver_parallel';result.append(request)
    if len(result)!=22:raise ValueError('Strong counter macro count changed')
    return result


def storage_evidence(component):
    code="""import sys,json
from pathlib import Path
sys.path.insert(0,'scripts');import build_strong_counter_storage_v229 as p
out=Path(sys.argv[1]);i=p.bound(out);r=json.loads((out/'summary.json').read_text())
if json.loads((out/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False) or not r['component_physical_rc_passed'] or any(p.sha(out/n)!=h for n,h in r['files'].items()) or any(p.sha(p.ROOT/n)!=h for n,h in r['extracted_files'].items()):raise ValueError('Require exact qualified guarded NAND8 body-contact storage')
files=[out/'manifest.json',out/'summary.json',out/'state.json',*[out/n for n in r['files']],*[p.ROOT/n for n in r['extracted_files']],*[p.ROOT/n for n in i['inputs']]]
print(json.dumps(dict(identity=i,report=r,files={str(f.relative_to(p.ROOT)):p.sha(f) for f in files})))
"""
    p=subprocess.run([original.repaired.CAD,'-c',code,str(component)],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:raise ValueError('Strong native storage admission refused: '+p.stderr[-2200:])
    return json.loads(p.stdout)


def prepare(parent,component):
    m=prior.bound(parent);i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False) or r.get('compact_counter_physical_passed') is not True:raise ValueError('Require complete passing direct-feedback physical counter')
    if any(sha(parent/n)!=h for n,h in r['files'].items()):raise ValueError('Original counter geometry changed')
    record=storage_evidence(component);si=record['identity'];sr=record['report']
    row=dict(sr['physical'],ports=si['anchors'],macro=STORAGE,gds_sha256=sr['extraction']['gds_sha256'],lef_sha256=sha(component/(STORAGE+'.lef')))
    cells=strengthened_cells(i['cells']);macros=deepcopy(i['macros']);macros[STORAGE]=original.macro(STORAGE,component,row)
    macros={name:macros[name] for name in sorted({c['model'] for c in cells})}
    compact=strong_plan(cells,macros,original.default_plan());original.source(cells,macros);witness=native_master_witness(macros)
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]+[ROOT/n for n in {*i['inputs'],*record['files']}]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),component=str(component.relative_to(ROOT)),cells=cells,macros=macros,**compact,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files={**i['pdk_files'],**si['external_files']},tools=i['tools'],cad=i['cad'],
        native_master_witness=witness,storage_cells_strengthened=sorted(Q_TAGS),request_drivers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or native.environment.tools()!=i['tools'] or sha(Path(original.repaired.CAD))!=i['cad']['sha256']):raise ValueError('Strong counter physical context changed')
    original_i=json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity']
    if i['cells']!=strengthened_cells(original_i['cells']) or len(i['cells'])!=22:raise ValueError('Strong counter source topology changed')
    expected=strong_plan(i['cells'],i['macros'],original.default_plan())
    if any(i[k]!=expected[k] for k in expected):raise ValueError('Strong counter placement/routing cannot regenerate')
    return m


def draw(out,i):
    macros=i['macros'];cells=i['cells'];plan=i['configuration'];places=i['placements'];points=i['points'];buses=i['buses']
    for name,macro in macros.items():
        folder=ROOT/macro['folder'];names=sorted(hierarchy(folder,name));commands=['gds readonly false',f'gds read {{{folder/(name+".gds")}}}']
        for child in names:commands += [f'load {child} -silent',f'save {child}']
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
    for direct in i['direct_feedback']:
        start,end=direct['ends']
        for p in (start,end):compact_via(p['x_um'],p['y_um'])
        g.wire('metal4',start['x_um'],start['y_um'],start['x_um'],end['y_um'],direct['vertical_width_um'])
        g.wire('metal4',start['x_um'],end['y_um'],end['x_um'],end['y_um'],direct['width_um'])
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
    for direct in i['direct_feedback']:
        start=direct['ends'][0];net=direct['net'];x=round(start['x_um']/layout.GRID);y=round(start['y_um']/layout.GRID)
        lines.append(f'rlabel metal4 {x} {y} {x} {y} 0 {net}')
    lines.append('<< end >>');(out/(NAME+'.mag')).write_text('\n'.join(lines)+'\n');(out/(NAME+'.sch.spice')).write_text(original.source(cells,macros))
    result=layout.qualify(out,NAME);raw=out/(NAME+'.raw.lef');raw.write_bytes((out/(NAME+'.lef')).read_bytes())
    types={p:('OUTPUT' if p in ['PREPARE','RESET_N','CLK'] else 'INPUT','SIGNAL') for p in PORTS if p not in ['VPWR','VGND']};types.update(VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
    text,pins=access.restrict(raw.read_text(),public,types);(out/(NAME+'.lef')).write_text(text)
    masks=native_master_witness(macros,out/(NAME+'.gds'),cells,places)
    return dict(result,native_master_witness=masks,macro=NAME,ports=public,integration_pins=pins,macro_count=len(cells),native_macro_types=len(macros),
                gds_sha256=sha(out/(NAME+'.gds')),lef_sha256=sha(out/(NAME+'.lef')),qualified_phy=False,electrical_qualification_passed=False)


def run(out):
    i=bound(out)['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial compact counter geometry')
        atomic(out/'state.json',dict(status='routing',qualified_phy=False));folder=out/NAME;folder.mkdir()
        try:
            row=draw(folder,i);atomic(folder/'summary.json',row);bound(out)
            result=dict(physical=row,passed=row['passed'],same_phase_logic=True,strong_native_storage_and_request=True,storage_cells_strengthened=i['storage_cells_strengthened'],request_drivers=2,
                compact_counter_physical_passed=row['passed'],shared_wire_rc_qualified=False,counter_timing_qualified=False,qualified_phy=False,scope=SCOPE)
            result['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
            atomic(out/'summary.json',result);atomic(out/'state.json',dict(status='complete',passed=row['passed'],qualified_phy=False));return out
        except Exception as e:atomic(out/'state.json',dict(status='failed',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--component',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.component is None:p.error('--component required')
        out=prepare(out,a.component.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
