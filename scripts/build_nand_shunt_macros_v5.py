#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native NAND2-2/8 with larger 3x3 output MIM shunts and public M3 rails.

Use the exact LI stack access proved by the label-only transistor audit. Added
mcon/M1 access is routed outside native power rails before ascending to M2.
Native cell masks remain unchanged; top-level contacts and wires need fresh
DRC/LVS. These component geometries do not qualify clock timing.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import layout
import build_compound_drivers_v3 as native
import label_nand_mid_access_v2 as access
import restrict_macro_rails_v4 as abstract

ROOT=layout.ROOT
VERSION='native-nand-stack-output-mim-macro-physical-v2.4'
sha=native.sha
TAP=native.TAP


def plan():
    return dict(mid_center=[4.5,7.],out_center=[13.,7.],mid_column=9.,output_column=16.,ground_column=18.,
        mid_escape_y=10.8,out_escape_y=10.8,signal_y=[.8,1.48,2.16],power_y=3.,ground_y=-.8,
        signal_width=.32,mid_contact_width=.30,mid_wire_width=.18,drop_width=.4)


def name(short):
    if short not in ['nand2_2','nand2_8']:raise ValueError('Undeclared shunted native NAND')
    return 'openlvds_'+short+'_shunted_v2'


def source(short,library,private):
    model='sky130_fd_sc_hd__'+short;gate=access.source_with_mid(native.cell_definition(library,model),private)
    tap=native.cell_definition(library,TAP);order=gate.splitlines()[0].split()[2:];tap_order=tap.splitlines()[0].split()[2:]
    nets=dict(A='A',B='B',Y='Y',MID='MID',VPWR='VPWR',VPB='VPWR',VGND='VGND',VNB='VGND')
    text=gate+'\n'+tap+'\n.subckt '+name(short)+' A B Y VPWR VGND\n'
    text+='Xgate '+' '.join(nets[p] for p in order)+' '+model+'\n'
    for side in ['left','right']:text+='Xtap_'+side+' '+' '.join(nets[p] for p in tap_order)+' '+TAP+'\n'
    size=4 if short=='nand2_8' else 2
    text+=f'XCMID MID VGND sky130_fd_pr__cap_mim_m3_1 w={size} l={size}\n'
    text+='XCY Y VGND sky130_fd_pr__cap_mim_m3_1 w=3 l=3\n.ends '+name(short)+'\n'
    return text


def prepare(parent):
    m=json.loads((parent/'manifest.json').read_text());r=json.loads((parent/'summary.json').read_text())
    if (m['version']!=access.VERSION or not r['mid_topology_passed'] or not r['all_mid_nodes_have_existing_li_access']
        or any(sha(ROOT/n)!=h for n,h in {**m['inputs'],**m['code']}.items()) or m['tools']!=native.environment.tools()):
        raise ValueError('Native MID access proof changed')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd'
    files=[parent/'manifest.json',parent/'summary.json']
    for row in r['rows']:
        f=parent/row['model'];files += [f/n for n in ['reference.spice','lvs.log','labelled.spice',row['model']+'_mid_probe.ext']]
    code=[Path(__file__),Path(native.__file__),Path(access.__file__),Path(abstract.__file__),Path(abstract.geometry.__file__),
        Path(layout.__file__),ROOT/'scripts/lvs_utils.py',Path(native.environment.__file__)]
    pdks=[sc/n for n in ['lef/sky130_fd_sc_hd.lef','gds/sky130_fd_sc_hd.gds','spice/sky130_fd_sc_hd.spice']]
    pdks += [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),configuration=plan(),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code},
        pdk_files={str(p):sha(p) for p in pdks},tools=native.environment.tools())
    out=ROOT/'build/diagnostics/nand_shunt_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or native.environment.tools()!=i['tools']):
        raise ValueError('Shunted NAND physical inputs changed')
    return m


def draw(out,short,row,lef,library,gds,p):
    model='sky130_fd_sc_hd__'+short;top=name(short);gate=native.lef_cell(lef,model);tap=native.lef_cell(lef,TAP)
    layout.invoke_magic(out,f'gds readonly false\ngds read {{{gds}}}\nload {model} -silent\nsave {{{out/model}}}\nload {TAP} -silent\nsave {{{out/TAP}}}', 'native_cells')
    boxes={n:native.native_bbox(out/(n+'.mag')) for n in [model,TAP]};mid_size=4 if short=='nand2_8' else 2
    cap_names=[f'mim_stack_{mid_size}x{mid_size}_v2','mim_output_3x3_v2'];caps={}
    for cell,size in zip(cap_names,[mid_size,3]):
        layout.invoke_magic(out,f'''load {cell} -silent
box values 0 0 0 0
set p [sky130::sky130_fd_pr__cap_mim_m3_1_defaults]
dict set p w {size}
dict set p l {size}
sky130::sky130_fd_pr__cap_mim_m3_1_draw $p
save {cell}
''','pcell_'+cell)
        caps[cell]=layout.pcell_info(out/(cell+'.mag'))
    g=layout.Geometry();ports={};width=gate['width']+2*tap['width'];start=tap['width'];right=p['ground_column']
    for pin,y in zip(['A','B','Y'],p['signal_y']):
        px,py=native.signal_point(gate['pins'][pin]);x=start+px
        g.pad('viali',x,py,.17);g.pad('metal1',x,py,.4);g.via12(x,py)
        g.wire('metal2',x,py,x,y,p['drop_width']);g.via23(x,y)
        g.wire('metal3',.3,y,right,y,p['signal_width'])
        ports[pin]=dict(layer='metal3',x_um=.3,y_um=y,width_um=p['signal_width'])
    # The small mcon landing fits above the native M1 ground rail. Its long
    # M1 escape supplies minimum area; the larger via12 is outside the row.
    landing=min(row['existing_li_access'].values(),key=lambda v:(-v['coordinate_um'][1],abs(v['coordinate_um'][0]-gate['width']/2)))
    mx,my=landing['coordinate_um'];mx+=start
    g.pad('viali',mx,my,.17);g.pad('metal1',mx,my,p['mid_contact_width'])
    g.wire('metal1',mx,my,p['mid_column'],my,p['mid_wire_width']);g.via12(p['mid_column'],my)
    g.wire('metal2',p['mid_column'],my,p['mid_column'],p['mid_escape_y'],p['drop_width']);g.via23(p['mid_column'],p['mid_escape_y'])
    for pin,y,source_y in [('VGND',p['ground_y'],0.),('VPWR',p['power_y'],gate['height'])]:
        for x in [tap['width']/2,width-tap['width']/2]:
            g.via12(x,source_y);g.wire('metal2',x,source_y,x,y,p['drop_width']);g.via23(x,y)
        g.wire('metal3',.3,y,right,y,.6);ports[pin]=dict(layer='metal3',x_um=.3,y_um=y,width_um=.6)
    for cell,center,escape,column in zip(cap_names,[p['mid_center'],p['out_center']],
                                       [p['mid_escape_y'],p['out_escape_y']],[p['mid_column'],p['output_column']]):
        info=caps[cell];cx,cy=center;_,x,y=info['ports']['C1'];x+=cx;y+=cy
        g.wire('metal4',x,y,x,escape,.6);g.via34(x,escape)
        g.wire('metal3',x,escape,column,escape,.4);g.via23(column,escape)
        if column==p['output_column']:
            g.wire('metal2',column,escape,column,p['signal_y'][2],p['drop_width']);g.via23(column,p['signal_y'][2])
        _,x,y=info['ports']['C2'];x+=cx;y+=cy
        g.wire('metal3',x,y,right,y,.4);g.via23(right,y)
        g.wire('metal2',right,y,right,p['ground_y'],p['drop_width']);g.via23(right,p['ground_y'])
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rects]]
    instances=[(TAP,'tap_left',0.,0.,boxes[TAP]),(model,'gate',start,0.,boxes[model]),(TAP,'tap_right',width-tap['width'],0.,boxes[TAP])]
    instances += [(cell,tag,*center,caps[cell]['bbox']) for cell,tag,center in zip(cap_names,['mid_cap','out_cap'],[p['mid_center'],p['out_center']])]
    for cell,instance,x,y,box in instances:
        lines += [f'use {cell} {instance}','timestamp 0',f'transform 1 0 {round(x/layout.GRID)} 0 1 {round(y/layout.GRID)}',
            'box '+' '.join(str(round(v/layout.GRID)) for v in box)]
    lines.append('<< labels >>')
    for n,(pin,point) in enumerate(ports.items(),1):
        x=round(point['x_um']/layout.GRID);y=round(point['y_um']/layout.GRID)
        lines += [f'rlabel metal3 {x} {y} {x} {y} 0 {pin}',f'port {n} nsew']
    lines.append('<< end >>');(out/(top+'.mag')).write_text('\n'.join(lines)+'\n')
    (out/(top+'.sch.spice')).write_text(source(short,library,row['private_source_node']))
    result=layout.qualify(out,top);raw=out/(top+'.raw.lef');raw.write_bytes((out/(top+'.lef')).read_bytes())
    types=dict(A=('INPUT','SIGNAL'),B=('INPUT','SIGNAL'),Y=('OUTPUT','SIGNAL'),VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
    text,pins=abstract.restrict(raw.read_text(),ports,types);(out/(top+'.lef')).write_text(text)
    return dict(result,macro=top,model=model,ports=ports,integration_pins=pins,stack_landing=landing,
        gds_sha256=sha(out/(top+'.gds')),lef_sha256=sha(out/(top+'.lef')),qualified_phy=False,electrical_qualification_passed=False)


def run(out):
    m=bound(out);i=m['identity'];parent=ROOT/i['parent'];report=json.loads((parent/'summary.json').read_text())
    sc=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd';lef=(sc/'lef/sky130_fd_sc_hd.lef').read_text();library=(sc/'spice/sky130_fd_sc_hd.spice').read_text()
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior shunted NAND geometry')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n');rows=[]
        for row in report['rows']:
            short=row['model'].removeprefix('sky130_fd_sc_hd__');folder=out/name(short);folder.mkdir()
            result=draw(folder,short,row,lef,library,sc/'gds/sky130_fd_sc_hd.gds',i['configuration']);rows.append(result)
            (folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        bound(out);result=dict(rows=rows,passed=all(r['passed'] for r in rows),qualified_phy=False,electrical_qualification_passed=False,
            scope='Native NAND gates with actual contacts, stack/output MIM shunts and M3 interfaces; geometry/connectivity only, no RC or clock timing admission')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=result['passed'],qualified_phy=False))+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
