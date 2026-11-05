#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Stacked NMOS-LVT/P-regular TG with balanced local M1 data routes."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import inspect_tg_device_pcells_v10 as primitives
import layout
from reduce_rc import number
import extract_native_flat_v4 as extraction
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from lvs_utils import strict_setup, clean_match
from spice_library import checked_netlist

ROOT = layout.ROOT
sha = primitives.sha
VERSION = 'stacked-mirrored-nlvt-tg-local-m1-data-physical-rc-v26.1'
CONTEXT = 'stacked_nlvt_tg_v26'
NAME = 'openlvds_tg_quad_stacked_nlvt_v26'
PORTS = ['A', 'Z', 'EN', 'ENB', 'VPWR', 'VGND']
N = 'sky130_fd_pr__nfet_01v8_lvt'
P = 'sky130_fd_pr__pfet_01v8'


def schematic():
    return (f'.subckt {NAME} '+ ' '.join(PORTS)+'\n'
            f'XN A EN Z VGND {N} w=1.68 l=.15 ad=.4872 as=.4872 pd=3.94 ps=3.94\n'
            f'XP Z ENB A VPWR {P} w=3.36 l=.15 ad=.9744 as=.9744 pd=7.3 ps=7.3\n'
            f'.ends {NAME}\n')


def native_check(text):
    defs = layout.circuits(text)
    if len(defs) != 1:
        raise ValueError('Require one flat native TG extraction')
    ports, devices = next(iter(defs.values()))
    if set(ports) != set(PORTS) or len(devices) != 2:
        raise ValueError('Native TG lost a public port or transistor')
    seen = set()
    for _, nodes, model, params in devices:
        if model in seen or model not in (N, P):
            raise ValueError('Native TG device model changed')
        seen.add(model)
        gate, body, ends, w, area, perimeter = ('EN', 'VGND', {'A', 'Z'}, 1.68, .4872, 3.94) if model == N else ('ENB', 'VPWR', {'A', 'Z'}, 3.36, .9744, 7.3)
        expected = dict(w=w, l=.15, ad=area, **{'as': area}, pd=perimeter, ps=perimeter)
        if nodes[1] != gate or nodes[3] != body or {nodes[0], nodes[2]} != ends or {k: float(v) for k, v in params.items()} != expected:
            raise ValueError('Native TG terminals, dimensions or junctions changed')
    return dict(two_native_mos_preserved=True, actual_junctions_match_standalone_pcells=True)


def native_evidence(evidence):
    r = json.loads((evidence/'summary.json').read_text()); i = r['identity']
    if (evidence.parent != ROOT/'build/diagnostics/nlvt_data_path_verification_v25'
            or not r['all_declared_cases_consumed'] or r['qualified_phy']):
        raise ValueError('Require complete independently verified NMOS-LVT diagnostic')
    parent = ROOT/i['parent']
    code = 'import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import verify_nlvt_data_path_v25 as p; assert p.verify(Path(sys.argv[2]))==Path(sys.argv[3])'
    subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'), '-c', code, str(ROOT), str(parent), str(evidence)], check=True)
    row = next(x for x in r['rows'] if x['task']['spec']['profile'] == 'data_nlvt')
    if (row['result']['zero_code_fast_quarter_headroom_ps'] >= 0 or not row['result']['terminal_screen_passed']
            or not row['result']['control_settling_passed']):
        raise ValueError('Require the measured timing-only failure before routing revision')
    pm = json.loads((parent/'manifest.json').read_text())['identity']
    paths = [evidence/'summary.json', parent/'manifest.json']
    paths += [ROOT/n for n in i['inputs']]+[ROOT/n for n in pm['inputs']]
    return paths, dict(pm['pdk_files'], **pm['external_files'])


def prepare(evidence):
    paths, external = native_evidence(evidence)
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A'
    technology = [p for p in (pdk/'libs.tech/magic').rglob('*') if p.is_file()]
    technology += [pdk/'libs.tech/netgen/sky130A_setup.tcl']
    code = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                   if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), p_center_y_um=4.8,
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
                    code={str(p.relative_to(ROOT)): sha(p) for p in code},
                    external_files=dict(external, **{str(p):sha(p) for p in technology}), tools=primitives.environment.tools())
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    (out/(NAME+'.sch.spice')).write_text(schematic())
    return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['p_center_y_um'] != 4.8
            or any(sha(ROOT/n) != h for n, h in {**i['inputs'], **i['code']}.items())
            or any(sha(Path(n)) != h for n, h in i['external_files'].items())
            or primitives.environment.tools() != i['tools'] or (out/(NAME+'.sch.spice')).read_text() != schematic()):
        raise ValueError('Stacked NMOS-LVT TG context changed')
    return i


def wire_loading(text):
    # Diagnostic upper tally: count explicit coupling in full at both public
    # conductors after R connectivity grouping; retain every element in RC.
    rows = [line.split('$',1)[0].split() for line in text.splitlines()]
    parents = {}
    def root(n):
        parents.setdefault(n,n)
        if parents[n]!=n:parents[n]=root(parents[n])
        return parents[n]
    for w in rows:
        if w and w[0].startswith('R'):
            parents[root(w[2])]=root(w[1])
    ports = {root(p):p for p in PORTS}
    if len(ports)!=len(PORTS):raise ValueError('R mesh shorts distinct TG ports')
    caps = {p:0. for p in PORTS}; cross = 0.
    for w in rows:
        if w and w[0].startswith('C'):
            a,b=root(w[1]),root(w[2]); value=number(w[3])*1e15
            for n in (a,b):
                if n in ports:caps[ports[n]]+=value
            if {ports.get(a),ports.get(b)}=={'A','Z'}:cross+=value
    return dict(wire_capacitance_upper_tally_ff=caps,az_coupling_ff=cross,excludes_native_mos_capacitance=True)


def draw(out, i):
    cells = [(N,1.68,'stacked_n168_nlvt_v26',0.,1), (P,3.36,'stacked_p336_regular_v26',i['p_center_y_um'],-1)]
    commands = []
    for model,w,cell,_,_ in cells:
        commands += [f'load {cell} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',
                     f'dict set p w {w}','dict set p l 0.15','dict set p botc 0',f'sky130::{model}_draw $p',
                     f'save {cell}',f'gds write {cell}.gds']
    layout.invoke_magic(out,'\n'.join(commands),'native_pcells')
    g=layout.Geometry();uses=[];interfaces={};recipes=[]
    for model,w,cell,cy,flip in cells:
        info=layout.pcell_info(out/(cell+'.mag'))
        if set(info['ports'])!={'D','G','S','B'}:raise ValueError('Native PCell interface changed')
        interfaces[model]={p:(flip*v[1],cy+v[2]) for p,v in info['ports'].items()}
        uses.append((cell,'nmos' if model==N else 'pmos',cy,flip,info['bbox']))
        recipes.append(dict(model=model,w=w,l=.15,cell=cell,center_y_um=cy,mirror_x=flip==-1,geometry=info))
    points={'A':[],'Z':[]}
    for model,dnet,snet in ((N,'A','Z'),(P,'Z','A')):
        for pin,net in (('D',dnet),('S',snet)):
            x,y=interfaces[model][pin];column=-.5 if net=='A' else .5
            g.wire('metal1',x,y,column,y,.18);points[net].append((column,y))
    ports={}
    for net in ('A','Z'):
        column=-.5 if net=='A' else .5;via=-.6 if net=='A' else .6;public=-1.6 if net=='A' else 1.6
        ys=[y for _,y in points[net]]
        g.wire('metal1',column,min(ys),column,max(ys),.18)
        g.wire('metal1',column,2.1,via,2.1,.18);g.via12(via,2.1);g.via23(via,2.1)
        g.wire('metal3',via,2.1,public,2.1,.4)
        ports[net]=dict(layer='metal3',x_um=public,y_um=2.1,width_um=.4)
    for model,net,column,yport in ((N,'EN',-1.6,.8),(P,'ENB',1.6,7.6)):
        x,y=interfaces[model]['G'];escape=y+.5
        g.wire('metal1',x,y,x,escape,.18);g.via12(x,escape)
        g.wire('metal2',x,escape,column,escape,.4);g.wire('metal2',column,escape,column,yport,.4);g.via23(column,yport)
        public=column-.4 if model==N else column+.4
        g.wire('metal3',column,yport,public,yport,.4)
        ports[net]=dict(layer='metal3',x_um=public,y_um=yport,width_um=.4)
    for model,net,yport in ((N,'VGND',-2.2),(P,'VPWR',3.1)):
        x,y=interfaces[model]['B']
        g.pad('locali',x,y,.33);g.pad('viali',x,y,.17);g.pad('metal1',x,y,.4);g.via12(x,y)
        g.wire('metal2',x,y,x,yport,.4);g.via23(x,yport);g.wire('metal3',x-.4,yport,x+.4,yport,.4)
        ports[net]=dict(layer='metal3',x_um=x-.4,y_um=yport,width_um=.4)
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rectangles in g.layers.items():lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rectangles]]
    for cell,tag,cy,flip,box in uses:
        lines += [f'use {cell} {tag}','timestamp 0',f'transform {flip} 0 0 0 1 {round(cy/layout.GRID)}',
                  'box '+' '.join(str(round(v/layout.GRID)) for v in box)]
    lines += ['<< labels >>']
    for index,pin in enumerate(PORTS,1):
        p=ports[pin];x,y=round(p['x_um']/layout.GRID),round(p['y_um']/layout.GRID)
        lines += [f'rlabel metal3 {x} {y} {x} {y} 0 {pin}',f'port {index} nsew']
    (out/(NAME+'.mag')).write_text('\n'.join(lines+['<< end >>','']))
    (out/'primitive_geometry.json').write_text(json.dumps(recipes,indent=2)+'\n')
    return {p:ports[p] for p in PORTS}


def run(out):
    i = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior or partial TG physical evidence')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        ports = draw(out, i)
        physical = layout.qualify(out, NAME)
        (out/'physical.json').write_text(json.dumps(physical, indent=2)+'\n')
        if not physical['passed']:
            raise ValueError('Compact TG physical DRC/LVS failed; retain evidence')
        native = native_check((out/(NAME+'.lvs.spice')).read_text())
        digest = hashlib.sha256((out/(NAME+'.gds')).read_bytes()+Path(extraction.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists():
            raise ValueError('Retain prior TG extraction')
        rc = extraction.extract(NAME, out/(NAME+'.gds'), sha(out/'manifest.json'), ports=ports, source_scope=sha(out/(NAME+'.sch.spice')))
        (out/'extraction.json').write_text(json.dumps(rc, indent=2)+'\n')
        text = checked_netlist(rc)
        if not audit(text)['elementwise_passive_passed']:
            raise ValueError('Compact TG RC failed passivity')
        collapsed = out/'wire_collapsed.spice'; collapsed.write_text(collapse(text))
        setup = strict_setup(out/'rc_setup.tcl', Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        log = out/'rc_lvs.log'
        p = subprocess.run(['netgen', '-batch', 'lvs', f'{collapsed} {NAME}', f'{out/(NAME+".sch.spice")} {NAME}', str(setup), str(log)], cwd=out, capture_output=True, text=True)
        (out/'rc_console.log').write_text(p.stdout+p.stderr)
        if not clean_match(log.read_text() if log.exists() else '', p.returncode):
            raise ValueError('Compact TG RC topology failed strict LVS')
        bound(out)
        report = dict(physical=physical, ports=ports, native=native, extraction=rc, rc_topology_passed=True,
                      component_physical_rc_passed=True, qualified_phy=False, electrical_qualification_passed=False,
                      scope='Stacked mirrored NMOS-LVT/P-regular TG with balanced M1 data routes and fresh passive component RC; no bank timing or PHY admission')
        report['wire_loading'] = wire_loading(text)
        report['files'] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name not in ('.execution.lock', 'state.json')}
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
        return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run', 'campaign']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); out = a.artifact.resolve()
    if a.action in ('prepare', 'campaign'):
        out = prepare(out); print(out, flush=True)
    if a.action in ('run', 'campaign'):
        print(run(out), flush=True)
