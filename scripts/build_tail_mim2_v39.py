#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Physical 2x2 balancing MIM with safe M4 escapes and public M3 access."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import verify_nlvt_guard2_v35 as reference

physical = reference.physical
native = physical.previous.tg
ROOT = physical.ROOT
sha = physical.sha
VERSION = 'native-tail-mim2-metal4-escape-and-fresh-rc-v39.1'
CONTEXT = 'tail_mim2_v39'
NAME = 'openlvds_tail_mim2_v39'
CAP = physical.CAP
PORTS = ['A','VGND']


def schematic():
    return f'.subckt {NAME} A VGND\nXcap A VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n.ends {NAME}\n'


def native_check(text):
    definitions = native.layout.circuits(text)
    if len(definitions) != 1: raise ValueError('Require one complete flat native tail MIM')
    ports,devices = next(iter(definitions.values()))
    if set(ports) != set(PORTS) or len(devices) != 1: raise ValueError('Tail MIM ports or primitive count changed')
    _,nodes,model,params = devices[0]
    if (set(nodes) != set(PORTS) or len(nodes) != 2 or model != 'sky130_fd_pr__cap_mim_m3_1'
            or {k:float(v) for k,v in params.items()} != dict(w=2.,l=2.)):
        raise ValueError('Tail MIM native model, size or terminals changed')
    return dict(one_native_mim=True,native_dimensions_um=[2,2],tail_to_ground_terminals_verified=True)


def masks(parent,candidate):
    import klayout.db as db
    a=db.Layout();a.read(str(parent/(CAP+'.gds')))
    b=db.Layout();b.read(str(candidate));top=b.cell(NAME);child=b.cell(CAP)
    if a.dbu != b.dbu or top is None or child is None: raise ValueError('Tail MIM primitive or grid changed')
    instances=list(top.each_inst())
    if len(instances) != 1 or instances[0].cell_index != child.cell_index() or instances[0].trans != db.Trans() or instances[0].is_regular_array():
        raise ValueError('Tail MIM native primitive placement changed')
    layers={(l.get_info(i).layer,l.get_info(i).datatype) for l in (a,b) for i in l.layer_indexes()}
    for key in layers:
        def region(layout,cell):
            i=layout.find_layer(*key)
            return db.Region() if i is None else db.Region(cell.begin_shapes_rec(i)).merged()
        if not (region(a,a.cell(CAP))^region(b,child)).is_empty(): raise ValueError('Tail MIM native masks changed')
    return dict(all_native_mim_masks_identical=True,native_primitive_placement_verified=True)


def prepare(evidence):
    i=reference.bound(evidence);parent=ROOT/i['parent'];pi=physical.bound(parent)
    info=native.layout.pcell_info(parent/(CAP+'.mag'))
    if {p:(v[1],v[2]) for p,v in info['ports'].items()} != {'C1':(-.88,0.),'C2':(1.82,0.)}:
        raise ValueError('Native 2x2 MIM pin coordinates changed')
    # The v38 pads at -2 um fail capm.11; -3 um clears the 1.34 um MiM-to-unrelated-M3 spacing.
    ports={p:dict(layer='metal3',x_um=x,y_um=-3.,width_um=.6) for p,x in [('A',-.88),('VGND',1.82)]}
    paths=[evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in i['inputs']],parent/(CAP+'.mag'),parent/(CAP+'.gds')]
    paths += [ROOT/n for n in pi['inputs']]
    code=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                 if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),parent=str(parent.relative_to(ROOT)),ports=ports,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={str(p.relative_to(ROOT)):sha(p) for p in code},
                  tools=pi['tools'],external_files=pi['external_files'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/(NAME+'.sch.spice')).write_text(schematic())
    return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n,h in {**i['inputs'],**i['code']}.items())
            or any(sha(Path(n)) != h for n,h in i['external_files'].items())
            or native.primitives.environment.tools() != i['tools'] or (out/(NAME+'.sch.spice')).read_text() != schematic()):
        raise ValueError('Tail MIM physical context changed')
    return i


def run(out):
    i=bound(out);parent=ROOT/i['parent'];layout=native.layout
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists(): raise ValueError('Retain existing or partial tail MIM evidence')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        shutil.copy2(parent/(CAP+'.mag'),out/(CAP+'.mag'))
        g=layout.Geometry()
        for pin in i['ports'].values():
            x=pin['x_um'];y=pin['y_um']
            # Descend to M3 only below the capacitor, never through its plates.
            g.wire('metal4',x,0.,x,y,.6);g.via34(x,y)
        lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
        for layer,rectangles in g.layers.items():
            lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rectangles]]
        bb=layout.pcell_info(out/(CAP+'.mag'))['bbox']
        lines += [f'use {CAP} cap','timestamp 0','transform 1 0 0 0 1 0','box '+' '.join(str(round(x/layout.GRID)) for x in bb),'<< labels >>']
        for index,(pin,p) in enumerate(i['ports'].items(),1):
            x,y=round(p['x_um']/layout.GRID),round(p['y_um']/layout.GRID)
            lines += [f'rlabel metal3 {x} {y} {x} {y} 0 {pin}',f'port {index} nsew']
        (out/(NAME+'.mag')).write_text('\n'.join(lines+['<< end >>','']))
        result=layout.qualify(out,NAME)
        (out/'physical.json').write_text(json.dumps(result,indent=2)+'\n')
        if not result['passed']: raise ValueError('Tail MIM DRC/LVS failed; retain evidence')
        geometry=masks(parent,out/(NAME+'.gds'));device=native_check((out/(NAME+'.lvs.spice')).read_text())
        digest=hashlib.sha256((out/(NAME+'.gds')).read_bytes()+Path(native.extraction.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists(): raise ValueError('Retain existing tail MIM RC')
        rc=native.extraction.extract(NAME,out/(NAME+'.gds'),sha(out/'manifest.json'),ports=i['ports'],source_scope=sha(out/(NAME+'.sch.spice')))
        (out/'extraction.json').write_text(json.dumps(rc,indent=2)+'\n');text=native.checked_netlist(rc)
        if not native.audit(text)['elementwise_passive_passed']: raise ValueError('Tail MIM RC failed passivity')
        collapsed=out/'wire_collapsed.spice';collapsed.write_text(native.collapse(text))
        setup=native.strict_setup(out/'rc_setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        log=out/'rc_lvs.log'
        p=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {NAME}',f'{out/(NAME+".sch.spice")} {NAME}',str(setup),str(log)],cwd=out,capture_output=True,text=True)
        (out/'rc_console.log').write_text(p.stdout+p.stderr)
        if not native.clean_match(log.read_text() if log.exists() else '',p.returncode): raise ValueError('Tail MIM RC topology failed strict LVS')
        bound(out)
        report=dict(physical=result,primitive_masks=geometry,native=device,extraction=rc,rc_topology_passed=True,
                    component_physical_rc_passed=True,qualified_phy=False,electrical_qualification_passed=False,
                    scope='Physical 2x2 balancing MIM with safe M4 escapes to public M3 pins and fresh passive RC; no bank timing or PHY qualification')
        report['files']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
        return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
