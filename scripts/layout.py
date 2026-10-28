#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Generate connected analog macros from the SAME transistor-level schematics.

Pinned Magic PCells provide devices, contacts, and body guards. Deterministic
M1 fanout / M2 drops / M3 buses provide actual interconnect. MIM top terminals
escape on M4 before descending outside the capacitor (never short its plates).
DRC and LVS are mandatory; generation alone is not a qualification result.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from lvs_utils import schematic_parameters,clean_match,strict_setup

ROOT=Path(__file__).resolve().parents[1]
GRID=.005

def circuits(text):
    definitions={};current=None
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('*'): continue
        words=line.split()
        if words[0].lower()=='.subckt':
            current=words[1];definitions[current]=(words[2:],[])
        elif words[0].lower()=='.ends': current=None
        elif current:
            if words[0][0].upper()!='X':
                raise ValueError(f'Implementation contains a non-PDK element: {line}')
            first=next((i for i,w in enumerate(words) if '=' in w),len(words))
            model=words[first-1];nodes=words[1:first-1]
            params=dict(w.split('=',1) for w in words[first:])
            definitions[current][1].append((words[0],nodes,model,params))
    for parent,(_,instances) in definitions.items():
        for instance,nodes,model,_ in instances:
            expected=len(definitions[model][0]) if model in definitions else (
                4 if 'fet_' in model else 3 if 'res_' in model else 2 if 'cap_mim' in model else None)
            if expected is not None and len(nodes)!=expected:
                raise ValueError(f'{parent}/{instance}: {model} expects {expected} terminals, got {len(nodes)}')
    return definitions

def flatten(defs,top):
    ports=defs[top][0];leaves=[]
    def recurse(model,mapping,prefix):
        for instance,nodes,child,params in defs[model][1]:
            translated=[mapping.get(n,prefix+'__'+n) for n in nodes]
            if child in defs:
                recurse(child,dict(zip(defs[child][0],translated)),prefix+'__'+instance)
            elif child.startswith('sky130_fd_pr__'):
                leaves.append(dict(name=prefix+'__'+instance,nodes=translated,model=child,params=params))
            else: raise ValueError(f'{child}: harden digital standard-cell blocks separately')
    recurse(top,dict(zip(ports,ports)),top)
    # Limit physical gate width to bound poly resistance at 800 Mb/s. Parallel
    # fingers retain the schematic's total W/L, with exact 5 nm grid geometry.
    fingers=[]
    for d in leaves:
        if 'nfet' not in d['model'] and 'pfet' not in d['model']:
            fingers.append(d);continue
        w=float(d['params']['w']);n=math.ceil(w/8.)
        while abs(w/n/GRID-round(w/n/GRID))>1e-6:n+=1
        for i in range(n):
            finger=dict(d,name=d['name']+f'_F{i}',params=dict(d['params'],w=f'{w/n:g}'))
            fingers.append(finger)
    return ports,fingers

def primitive_key(device):
    return device['model'],float(device['params']['w']),float(device['params']['l'])

def schematic_text(top,ports,devices):
    lines=['* SPDX-License-Identifier: GPL-3.0-only',f'.subckt {top} '+' '.join(ports)]
    for d in devices:
        lines.append('X'+d['name']+' '+' '.join(d['nodes'])+' '+d['model']+' '+
                     ' '.join(f'{k}={v}' for k,v in schematic_parameters(d).items()))
    return '\n'.join(lines+[f'.ends {top}',''])

def invoke_magic(out,body,logname):
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/magic/sky130A.magicrc'
    tcl=out/(logname+'.tcl')
    tcl.write_text('drc off\ncrashbackups disable\nlocking disable\n'+body+'\nquit -noprompt\n')
    with (out/(logname+'.log')).open('w') as log:
        result=subprocess.run(['magic','-dnull','-noconsole','-rcfile',str(tech),str(tcl)],
                              cwd=out,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError(f'Magic failed: {out}/{logname}.log')

def pcell_info(path):
    text=path.read_text();ports={};bounds=[]
    for line in text.splitlines():
        if line.startswith('rect '): bounds.append(list(map(int,line.split()[1:])))
        if line.startswith('rlabel '):
            w=line.split();ports[w[-1]]=(w[1],(int(w[2])+int(w[4]))/2*GRID,
                                        (int(w[3])+int(w[5]))/2*GRID)
    if not bounds: raise ValueError(f'Empty PCell {path}')
    bbox=[min(x[0] for x in bounds)*GRID,min(x[1] for x in bounds)*GRID,
          max(x[2] for x in bounds)*GRID,max(x[3] for x in bounds)*GRID]
    return dict(ports=ports,bbox=bbox)

class Geometry:
    def __init__(self): self.layers=defaultdict(list)
    def rect(self,layer,x0,y0,x1,y1):
        coords=[round(min(x0,x1)/GRID),round(min(y0,y1)/GRID),
                round(max(x0,x1)/GRID),round(max(y0,y1)/GRID)]
        if coords[2]<=coords[0] or coords[3]<=coords[1]: raise ValueError('Zero-area geometry')
        self.layers[layer].append(coords)
    def pad(self,layer,x,y,size): self.rect(layer,x-size/2,y-size/2,x+size/2,y+size/2)
    def wire(self,layer,x0,y0,x1,y1,width=.4):
        if x0!=x1 and y0!=y1: raise ValueError('Non-Manhattan wire')
        self.rect(layer,min(x0,x1)-width/2,min(y0,y1)-width/2,
                  max(x0,x1)+width/2,max(y0,y1)+width/2)
    def via12(self,x,y):
        self.pad('metal1',x,y,.4);self.pad('via1',x,y,.26);self.pad('metal2',x,y,.4)
    def via23(self,x,y):
        self.pad('metal2',x,y,.4);self.pad('via2',x,y,.28);self.pad('metal3',x,y,.4)
    def via34(self,x,y):
        self.pad('metal3',x,y,.6);self.pad('via3',x,y,.4);self.pad('metal4',x,y,.6)

def draw_macro(out,top,ports,devices,library):
    geometry=Geometry();uses=[];drops=defaultdict(list);cursor=10.;ymax=0.
    left_gap,right_gap=(2.5,2.5) if top in ['openlvds_dll_analog','openlvds_delay_line','openlvds_receiver_core'] else (5.,6.)
    for i,d in enumerate(devices):
        cell,info=library[primitive_key(d)];bb=info['bbox'];pw=info['ports']
        cx=cursor-bb[0]+left_gap;cursor=cx+bb[2]+right_gap;ymax=max(ymax,bb[3])
        uses.append((cell,f'I{i}',round(cx/GRID),0,[round(v/GRID) for v in bb]))
        model=d['model']
        if 'nfet' in model or 'pfet' in model:
            access=[('D',d['nodes'][0],-1.8),('G',d['nodes'][1],0.),
                    ('S',d['nodes'][2],1.8),('B',d['nodes'][3],-2.8)]
        elif 'res_' in model:
            access=[('R1',d['nodes'][0],-1.8),('R2',d['nodes'][1],1.8),('B',d['nodes'][2],-2.8)]
        elif 'cap_mim' in model:
            access=[('C1',d['nodes'][0],bb[0]-2.),('C2',d['nodes'][1],bb[2]+2.)]
        else: raise ValueError(model)
        for pin,net,dx in access:
            if pin not in pw: raise ValueError(f'{cell} missing {pin}: {pw}')
            layer,px,py=pw[pin]
            # Long-channel devices have contacts farther from the origin.
            # Keep the added via landing outside the PCell contact metal.
            if pin in ['D','S']:
                dx=(-1 if pin=='D' else 1)*max(abs(dx),abs(px)+.8)
            if pin=='B' and ('nfet' in model or 'pfet' in model):
                dx=-max(abs(dx),abs(pw['D'][1])+2.)
            px+=cx;track=cx+dx
            if 'cap_mim' in model:
                if pin=='C1':
                    geometry.wire('metal4',px,py,track,py,.6)
                    geometry.via34(track,py)
                else: geometry.wire('metal3',px,py,track,py,.6)
                geometry.via23(track,py)
            else:
                if pin=='B':
                    geometry.pad('locali',px,py,.33)
                    geometry.pad('viali',px,py,.17)
                    geometry.pad('metal1',px,py,.4)
                if pin=='G':
                    geometry.wire('metal1',px,py,px,py+.3,.18)
                    py+=.3
                geometry.wire('metal1',px,py,track,py,.18)
                geometry.via12(track,py)
            drops[net].append((track,py))
    # Keep buses above the tallest device including resistor guards and wells.
    origin=math.ceil(ymax+6.)
    internal=set(drops)-set(ports)
    fast_suffixes=['__DP','__DN','__XLS__L','__XLS__R','__XLS__AD','__XLS__AB','__XLS__INB','__XLS__L1','__XLS__R1']
    def priority(net):
        return next((i for i,s in enumerate(fast_suffixes) if net.endswith(s)),len(fast_suffixes)),net
    compact_internal=top in ['openlvds_driver_core','openlvds_dll_analog','openlvds_delay_line','openlvds_receiver_core']
    local_ports=top in ['openlvds_dll_analog','openlvds_delay_line','openlvds_receiver_core']
    net_order=list(ports)+sorted(internal,key=priority if compact_internal else None)
    labels=[];public={};y=origin
    # An unrelated PCell from another selected macro must not move this bus.
    below=min(library[primitive_key(d)][1]['bbox'][1] for d in devices)-6.
    ceiling=origin+sum((5. if n in ['VDDIO','VDDD','VSS'] else 3. if n in ['OUTP','OUTN'] else .4)+1.4 for n in ports)+6.
    for i,net in enumerate(net_order):
        if net not in drops: raise ValueError(f'Unconnected public port: {net}')
        points=drops[net];xs=[x for x,_ in points]
        width=5. if net in ['VDDIO','VDDD','VSS'] else 3. if net in ['OUTP','OUTN'] else .4
        if compact_internal and net not in ports:
            if priority(net)[0]<len(fast_suffixes):width=.8
            below-=width/2+.7;bus_y=below;below-=width/2+.7
        else:
            y+=width/2+.7;bus_y=y;y+=width/2+.7
        escape=local_ports and net in ports and net not in ['VDDIO','VDDD','VSS']
        left=width/2 if net in ports and not escape else min(xs)-1.
        geometry.wire('metal3',left,bus_y,max(xs)+1.,bus_y,width)
        for x,py in points:
            geometry.wire('metal2',x,py,x,bus_y)
            geometry.via23(x,bus_y)
        labelx=left if net in ports else min(xs)-.5
        label_y=bus_y;label_layer='metal3'
        if escape:
            geometry.via34(labelx,bus_y)
            geometry.wire('metal4',labelx,bus_y,labelx,ceiling,.6)
            label_y=ceiling;label_layer='metal4'
        labels.append((net,labelx,label_y,ports.index(net)+1 if net in ports else None,label_layer))
        if net in ports:public[net]=dict(layer=label_layer,x_um=labelx,y_um=label_y,width_um=.6 if escape else width)
    layout_height=max(y,ceiling if local_ports else y)-min(0,below)+4 if compact_internal else y+ymax+4
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rects in geometry.layers.items():
        lines.append(f'<< {layer} >>')
        lines.extend('rect '+' '.join(map(str,r)) for r in rects)
    for cell,instance,x,y,bb in uses:
        lines.extend([f'use {cell} {instance}','timestamp 0',f'transform 1 0 {x} 0 1 {y}',
                      'box '+' '.join(map(str,bb))])
    lines.append('<< labels >>')
    for net,lx,ly,port,label_layer in labels:
        lx=round(lx/GRID);ly=round(ly/GRID)
        lines.append(f'rlabel {label_layer} {lx} {ly} {lx} {ly} 0 {net}')
        if port: lines.append(f'port {port} nsew')
    lines.append('<< end >>')
    (out/(top+'.mag')).write_text('\n'.join(lines)+'\n')
    # Flattened schematic used for independent connectivity comparison.
    (out/(top+'.sch.spice')).write_text(schematic_text(top,ports,devices))
    return dict(width_um=cursor+4,height_um=layout_height,
                devices=len(devices),nets=len(net_order),ports=public)

def qualify(out,top):
    # Extract ordinary device netlist for LVS before parasitic extraction.
    body=f'''load {top}
select top cell
gds write {top}.gds
lef write {top}.lef
flatten {top}_flat
load {top}_flat
select clear
select top cell
box values -100um -100um 10000um 10000um
drc euclidean on
drc on
drc check
drc catchup
set errors [drc listall why]
set f [open {top}.drc.txt w]
puts $f $errors
close $f
set f [open {top}.drc_count.txt w]
puts $f [drc listall count total]
close $f
extract all
ext2spice lvs
ext2spice -o {top}.lvs.spice {top}_flat.ext
'''
    invoke_magic(out,body,'extract_'+top)
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    tech=strict_setup(out/(top+'.lvs_setup.tcl'),tech)
    report=out/(top+'.lvs.log')
    command=['netgen','-batch','lvs',f'{out}/{top}.lvs.spice {top}_flat',
             f'{out}/{top}.sch.spice {top}',str(tech),str(report)]
    result=subprocess.run(command,cwd=out,capture_output=True,text=True)
    (out/(top+'.netgen.log')).write_text(result.stdout+result.stderr)
    text=report.read_text() if report.exists() else ''
    drc=(out/(top+'.drc_count.txt')).read_text().strip()
    lvs=clean_match(text,result.returncode)
    return dict(drc_count=drc,lvs_passed=lvs,
                lvs_source_sha256=hashlib.sha256((out/(top+'.sch.spice')).read_bytes()).hexdigest(),
                lvs_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest() if report.exists() else None,
                passed=drc=='0' and lvs,gds=str((out/(top+'.gds')).relative_to(ROOT)))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--design',default='openlvds_driver_core,openlvds_receiver_core,openlvds_delay_line,openlvds_dll_analog,lvds_bias')
    p.add_argument('--keep-existing',action='store_true',help='Retain other qualified macros from the identical schematic revision')
    a=p.parse_args()
    source=(ROOT/'analog/openlvds.spice').read_bytes()
    fingerprint=hashlib.sha256(source+Path(__file__).read_bytes()+
                 (ROOT/'scripts/lvs_utils.py').read_bytes()+
                 (ROOT/'requirements.json').read_bytes()).hexdigest()
    out=ROOT/'build/layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    defs=circuits(source.decode());designs={}
    for top in a.design.split(','):
        designs[top]=flatten(defs,top)
    keys=sorted({primitive_key(d) for _,devs in designs.values() for d in devs})
    body=[];names={}
    for i,(model,w,l) in enumerate(keys):
        cell='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12]
        names[(model,w,l)]=cell
        # Remove only these generated cells to avoid accumulating old labels.
        (out/(cell+'.mag')).unlink(missing_ok=True)
        body.extend([f'load {cell} -silent','box values 0 0 0 0',
            f'set p [sky130::{model}_defaults]',f'dict set p w {w}',f'dict set p l {l}',
            *(['dict set p botc 0'] if 'nfet' in model or 'pfet' in model else []),
            f'sky130::{model}_draw $p',f'save {cell}'])
    invoke_magic(out,'\n'.join(body),'pcells')
    library={key:(name,pcell_info(out/(name+'.mag'))) for key,name in names.items()}
    results={}
    if a.keep_existing:
        previous=json.loads((ROOT/'build/layout/current.json').read_text())
        results={k:v for k,v in previous['designs'].items() if k not in designs}
        if any(not v.get('passed') for v in results.values()):raise ValueError('Cannot retain failed layouts')
        for name,info in results.items():
            pins,devices=flatten(defs,name)
            archived=(ROOT/info['gds']).with_suffix('.sch.spice')
            expected=schematic_text(name,pins,devices).encode()
            if not archived.exists() or archived.read_bytes()!=expected:
                raise ValueError(name+': schematic changed; regenerate this macro')
            info['retained_from_source_sha256']=previous['source_sha256']
    for top,(ports,devs) in designs.items():
        info=draw_macro(out,top,ports,devs,library)
        try: info.update(qualify(out,top))
        except (OSError,RuntimeError) as error: info.update(passed=False,error=str(error))
        results[top]=info
        print(top,json.dumps({k:v for k,v in info.items() if k!='ports'}),flush=True)
    summary=dict(source_sha256=hashlib.sha256(source).hexdigest(),fingerprint=fingerprint,
                 passed=all(v.get('passed',False) for v in results.values()),designs=results,
                 output=str(out.relative_to(ROOT)))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (ROOT/'build/layout/current.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
