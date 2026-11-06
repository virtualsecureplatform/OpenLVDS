#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Guard only the native NAND2B4 stack; retain the mirrored body-contact row.

Use only label/LVS-proven private LI. Each stack node has its own real MIM
and route; every native transistor and native cell mask remains unchanged.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import layout
import build_compound_drivers_v3 as native
import inspect_nand2b_access_v2 as access
import restrict_macro_rails_v4 as abstract

ROOT=layout.ROOT
VERSION='native-nand2b-3um-output-stack-guard-body-tap-row-v180.1'
sha=native.sha
TAP=native.TAP
VARIANTS={'nand2b_4_o3':('nand2b_4',3)}


def name(variant):
    if variant not in VARIANTS:raise ValueError('Unknown native shunted cell')
    return 'openlvds_'+variant+'_stack_guard_bodytap_v180'


def stack_reference(source):
    gate,mapping=access.reference(source)
    if mapping!={'a_215_47#':'MID0','a_27_47#':'MID1'}:raise ValueError('Native NAND2B stack/inverter identities changed')
    lines=gate.splitlines();lines[0]=' '.join(w for w in lines[0].split() if w!='MID1')
    gate='\n'.join(lines)+'\n'
    gate=re.sub(r'(?<!\S)MID1(?!\S)','a_27_47#',gate)
    return gate,{'a_215_47#':'MID0'}


def source(variant,library):
    short,size=VARIANTS[variant];model='sky130_fd_sc_hd__'+short
    gate,mapping=stack_reference(native.cell_definition(library,model));order=gate.splitlines()[0].split()[2:]
    tap=native.cell_definition(library,TAP);tap_order=tap.splitlines()[0].split()[2:]
    signal=[n for n in order if n not in ['VPWR','VGND','VPB','VNB'] and n not in mapping.values()]
    nets=dict(VPWR='VPWR',VPB='VPWR',VGND='VGND',VNB='VGND',**{n:n for n in signal+list(mapping.values())})
    text=gate+'\n'+tap+'\n.subckt '+name(variant)+' '+' '.join(signal+['VPWR','VGND'])+'\n'
    text+='Xgate '+' '.join(nets[n] for n in order)+' '+model+'\n'
    for side in ['left','right']:text+='Xtap_'+side+' '+' '.join(nets[n] for n in tap_order)+' '+TAP+'\n'
    for mid in mapping.values():text+=f'XCAP_{mid} {mid} VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n'
    output='X' if short.startswith('buf_') else 'Y'
    text+=f'XCAP_OUT {output} VGND sky130_fd_pr__cap_mim_m3_1 w={size} l={size}\n.ends '+name(variant)+'\n'
    return text,signal,mapping


def prepare(parent):
    m=json.loads((parent/'manifest.json').read_text());r=json.loads((parent/'summary.json').read_text())
    if m['version']!=access.VERSION or r['identity']!=m or not r['passed']:raise ValueError('Require native cell access proofs')
    if any(sha(ROOT/n)!=h for n,h in m['code'].items()) or any(sha(Path(n))!=h for n,h in m['pdk_files'].items()):raise ValueError('Access proof inputs changed')
    files=[parent/'manifest.json',parent/'summary.json']
    for row in r['rows']:
        for n,h in row['files'].items():
            if sha(ROOT/n)!=h:raise ValueError('Changed labelled native geometry/source')
            files.append(ROOT/n)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd'
    pdks=[sc/n for n in ['gds/sky130_fd_sc_hd.gds','lef/sky130_fd_sc_hd.lef','spice/sky130_fd_sc_hd.spice']]
    pdks += [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    code=[Path(__file__),Path(access.__file__),Path(native.__file__),Path(native.environment.__file__),Path(layout.__file__),Path(abstract.__file__),Path(abstract.geometry.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),variants=VARIANTS,inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        code={str(p.relative_to(ROOT)):sha(p) for p in code},pdk_files={str(p):sha(p) for p in pdks},tools=native.environment.tools())
    out=ROOT/'build/diagnostics/nand2b_stack_guard_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or native.environment.tools()!=i['tools']):raise ValueError('Native cell physical context changed')
    return m


def draw(folder,variant,row,library,lef,gds):
    short,size=VARIANTS[variant];model='sky130_fd_sc_hd__'+short;top=name(variant)
    text,signals,mapping=source(variant,library);gate=native.lef_cell(lef,model);tap=native.lef_cell(lef,TAP)
    layout.invoke_magic(folder,f'gds readonly false\ngds read {{{gds}}}\nload {model} -silent\nsave {{{folder/model}}}\nload {TAP} -silent\nsave {{{folder/TAP}}}', 'native_cells')
    boxes={n:native.native_bbox(folder/(n+'.mag')) for n in [model,TAP]};caps={}
    for dim in sorted({2,size}):
        cell=f'clock_mim_{dim}x{dim}_v2'
        layout.invoke_magic(folder,f'''load {cell} -silent
box values 0 0 0 0
set p [sky130::sky130_fd_pr__cap_mim_m3_1_defaults]
dict set p w {dim}
dict set p l {dim}
sky130::sky130_fd_pr__cap_mim_m3_1_draw $p
save {cell}
''','pcell_'+cell)
        caps[dim]=(cell,layout.pcell_info(folder/(cell+'.mag')))
    g=layout.Geometry();ports={};start=tap['width'];width=gate['width']+2*start;count=len(mapping)
    cap_start=max(7.,width+2.);right=cap_start+9*count+5.;power_y=3.6;ground_y=-.8
    output='X' if short.startswith('buf_') else 'Y';signal_y={pin:.72+.68*n for n,pin in enumerate(signals)}
    for pin,y in signal_y.items():
        if short=='nand3_2':
            px,py=dict(A=(.21,1.16),B=(1.25,1.175),C=(3.45,1.175),Y=(2.88,2.065))[pin]
            if not any(layer=='li1' and r[0]<=px-.085 and r[1]<=py-.085 and r[2]>=px+.085 and r[3]>=py+.085 for layer,r in gate['pins'][pin]):
                raise ValueError('NAND3 selected LI contact is outside its native pin')
        else:px,py=native.signal_point(gate['pins'][pin])
        x=start+px
        g.pad('viali',x,py,.17);g.pad('metal1',x,py,.4);g.via12(x,py)
        g.wire('metal2',x,py,x,y,.4);g.via23(x,y);g.wire('metal3',.3,y,right,y,.32)
        ports[pin]=dict(layer='metal3',x_um=.3,y_um=y,width_um=.32)
    for pin,y,source_y in [('VGND',ground_y,0.),('VPWR',power_y,gate['height'])]:
        for x in [start/2,width-start/2]:
            g.via12(x,source_y);g.wire('metal2',x,source_y,x,y,.4);g.via23(x,y)
        g.wire('metal3',.3,y,right,y,.6);ports[pin]=dict(layer='metal3',x_um=.3,y_um=y,width_um=.6)
    landings={};instances=[]
    for n,mid in enumerate(mapping.values()):
        candidates=row['private_nodes'][mid]['existing_li_access']
        # BUF private output has both P and N access; avoid a landing close to
        # the power rail. NAND3 stacks have distinct upper LI landings.
        eligible={k:v for k,v in candidates.items() if .55<=v['coordinate_um'][1]<=2.0}
        if short=='nand2b_4' and mid=='MID1':
            eligible={k:v for k,v in eligible.items() if v['coordinate_um'][0]>=.8}
        if not eligible:raise ValueError('No pre-proved safely accessible private LI')
        landing=min(eligible.values(),key=lambda v:(-v['coordinate_um'][1],abs(v['coordinate_um'][0]-gate['width']/2)))
        mx,my=landing['coordinate_um'];mx+=start;landings[mid]=landing;escape=12.+n
        g.pad('viali',mx,my,.17)
        if short=='nand3_2' and my<.71:g.rect('metal1',mx-.15,my-.13,mx+.15,my+.13)
        else:g.pad('metal1',mx,my,.30)
        # Drive-4 NAND landing is close to ground: escape in narrow M1 before
        # the larger via. NAND3/BUF can ascend directly on their own columns.
        column=-.8 if short=='nand3_2' and my<.71 else (width+1. if my<.64 else mx)
        if column!=mx:g.wire('metal1',mx,my,column,my,.18)
        g.via12(column,my);g.wire('metal2',column,my,column,escape,.4);g.via23(column,escape)
        cell,info=caps[2];cx,cy=cap_start+9*n,8.;_,x,y=info['ports']['C1'];x+=cx;y+=cy
        g.wire('metal4',x,y,x,escape,.6);g.via34(x,escape);g.wire('metal3',x,escape,column,escape,.4)
        instances.append((cell,'cap_'+mid,cx,cy,info['bbox']))
        _,x,y=info['ports']['C2'];x+=cx;y+=cy;g.wire('metal3',x,y,right,y,.4);g.via23(right,y)
        g.wire('metal2',right,y,right,ground_y,.4);g.via23(right,ground_y)
    cell,info=caps[size];cx,cy=cap_start+9*count,8.;escape=14.;column=right-1.
    _,x,y=info['ports']['C1'];x+=cx;y+=cy;g.wire('metal4',x,y,x,escape,.6);g.via34(x,escape)
    g.wire('metal3',x,escape,column,escape,.4);g.via23(column,escape)
    g.wire('metal2',column,escape,column,signal_y[output],.4);g.via23(column,signal_y[output])
    _,x,y=info['ports']['C2'];x+=cx;y+=cy;g.wire('metal3',x,y,right,y,.4);g.via23(right,y)
    g.wire('metal2',right,y,right,ground_y,.4);g.via23(right,ground_y);instances.append((cell,'cap_out',cx,cy,info['bbox']))
    # A complete mirrored native tap row puts p-substrate contacts below
    # every active-cell site. The row's separate lower nwell remains on VPWR.
    tap_count=round(width/tap['width']);tap_row_y=-.4;tap_power_y=tap_row_y-tap['height'];row_power_y=-4.
    if abs(tap_count*tap['width']-width)>layout.GRID/2:raise ValueError('Body tap row must fill exact native sites')
    if native.cell_definition(library,TAP).splitlines()[0].split()[2:]!=['VGND','VPWR']:raise ValueError('Native tap port order changed')
    for x in [start/2,width-start/2]:
        g.via12(x,tap_row_y);g.wire('metal2',x,tap_row_y,x,ground_y,.4);g.via23(x,ground_y)
        g.via12(x,tap_power_y);g.wire('metal2',x,tap_power_y,x,row_power_y,.4);g.via23(x,row_power_y)
    g.wire('metal3',-1.,row_power_y,width-start/2,row_power_y,.6)
    g.via23(-1.,row_power_y);g.wire('metal2',-1.,row_power_y,-1.,power_y,.4)
    g.via23(-1.,power_y);g.wire('metal3',-1.,power_y,.3,power_y,.6)
    marker='.ends '+top+'\n'
    if text.count(marker)!=1:raise ValueError('Native body-tap source boundary changed')
    extra=''.join(f'Xtap_bottom{i} VGND VPWR {TAP}\n' for i in range(tap_count))
    text=text.replace(marker,extra+marker)
    instances=[(TAP,'tap_left',0.,0.,boxes[TAP]),(model,'gate',start,0.,boxes[model]),(TAP,'tap_right',width-start,0.,boxes[TAP])]+instances
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in g.layers.items():lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rects]]
    for cell,tag,x,y,box in instances:
        lines += [f'use {cell} {tag}','timestamp 0',f'transform 1 0 {round(x/layout.GRID)} 0 1 {round(y/layout.GRID)}','box '+' '.join(str(round(v/layout.GRID)) for v in box)]
    for i in range(tap_count):
        x=i*tap['width'];box=boxes[TAP]
        lines += [f'use {TAP} tap_bottom{i}','timestamp 0',
            f'transform 1 0 {round(x/layout.GRID)} 0 -1 {round(tap_row_y/layout.GRID)}',
            'box '+' '.join(str(round(v/layout.GRID)) for v in box)]
    lines.append('<< labels >>')
    for n,(pin,p) in enumerate(ports.items(),1):
        x=round(p['x_um']/layout.GRID);y=round(p['y_um']/layout.GRID);lines += [f'rlabel metal3 {x} {y} {x} {y} 0 {pin}',f'port {n} nsew']
    lines.append('<< end >>');(folder/(top+'.mag')).write_text('\n'.join(lines)+'\n');(folder/(top+'.sch.spice')).write_text(text)
    result=layout.qualify(folder,top);raw=folder/(top+'.raw.lef');raw.write_bytes((folder/(top+'.lef')).read_bytes())
    types={pin:('OUTPUT' if pin==output else 'INPUT','SIGNAL') for pin in signals};types.update(VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
    text,pins=abstract.restrict(raw.read_text(),ports,types);(folder/(top+'.lef')).write_text(text)
    return dict(result,body_tap_row=dict(count=tap_count,mirrored=True,ground_y_um=tap_row_y,power_y_um=tap_power_y),macro=top,variant=variant,model=model,ports=ports,integration_pins=pins,private_landings=landings,
        gds_sha256=sha(folder/(top+'.gds')),lef_sha256=sha(folder/(top+'.lef')),qualified_phy=False,electrical_qualification_passed=False)


def run(out):
    m=bound(out);report=json.loads((ROOT/m['identity']['parent']/'summary.json').read_text());rows_by_model={r['model']:r for r in report['rows']}
    sc=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd';library=(sc/'spice/sky130_fd_sc_hd.spice').read_text();lef=(sc/'lef/sky130_fd_sc_hd.lef').read_text()
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior cell family geometry')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n');rows=[]
        for variant,(short,_) in VARIANTS.items():
            folder=out/name(variant);folder.mkdir();row=draw(folder,variant,rows_by_model['sky130_fd_sc_hd__'+short],library,lef,sc/'gds/sky130_fd_sc_hd.gds')
            rows.append(row);(folder/'summary.json').write_text(json.dumps(row,indent=2)+'\n')
        bound(out);result=dict(rows=rows,passed=all(r['passed'] for r in rows),qualified_phy=False,electrical_qualification_passed=False,
            scope='Two native NAND2B shunt variants: geometry/connectivity only; no native RC timing or clock backend admission')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=result['passed'],qualified_phy=False))+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2))
