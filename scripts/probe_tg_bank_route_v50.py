#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bring the full both2 bank through routing; full GDS/LVS/RC remain separate."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import build_tg_bank_floorplan_v49 as placement

ROOT=placement.ROOT
sha=placement.sha
VERSION='both2-route-complete-supply-adapter-and-native-domain-restore-v50.1'
CONTEXT='tg_bank_route_v50'
TEMPLATE=Path(__file__).with_name('tg_bank_route_v50.tcl')


def route_tcl(parent,out,plan):
    restore=[]
    for route in plan['fixed_routes']:
        if route['net']=='OUT':continue
        if route['net'] not in ('VPWR','VGND') or route['layer']!='met3':raise ValueError('Unexpected fixed supply bus')
        coords=' '.join(str(round(x*1000)) for x in route['rect'])
        restore += [f'set net [$block findNet {route["net"]}]','set wire [odb::dbSWire_create $net ROUTED]',
                    f'odb::dbSBox_create $wire [[$db getTech] findLayer met3] {coords} STRIPE']
    return TEMPLATE.read_text().replace('@PARENT@',str(parent)).replace('@OUT@',str(out)).replace('@RESTORE_POWER@','\n'.join(restore))


def prepare(parent):
    pi,tools=placement.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if not r['placement_passed'] or r['placement_geometry']['drc_count']!='0':raise ValueError('Require DRC-clean tapped placement')
    if any(sha(parent/n)!=h for n,h in r['files'].items()):raise ValueError('Placement outputs changed')
    # IN is already complete inside the native input rail; OUT has the fixed
    # bus proved by v49. Neither needs a synthetic router access pad.
    plan=pi['plan'];graph=pi['graph'];registry=ROOT/pi['parent']
    records=json.loads((registry/'summary.json').read_text())['cells']
    x,y=plan['placements']['u_input_inverse'];pin=records[placement.floorplan.INV]['pins']['A']['shapes'][0][1]
    actual=plan['ports']['IN']['rect'];expected=[x+pin[0],y+pin[1],x+pin[2],y+pin[3]]
    if not (expected[0]<=actual[0]<actual[2]<=expected[2] and expected[1]<=actual[1]<actual[3]<=expected[3]):
        raise ValueError('Native IN public port is not already connected to its input rail')
    paths=[parent/'manifest.json',parent/'summary.json',*[parent/n for n in r['files']],Path(__file__),TEMPLATE]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  regular_wire_nets=sorted((set(graph['ports'])|{n for c in graph['cells'] for n in c['pins'].values()})-{'IN','OUT'}),
                  openroad=tools['openroad'],scope='Router bring-up with exact cell/native domain restoration; no GDS/LVS/RC or timing admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'route.tcl').write_text(route_tcl(parent,out,plan));return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];parent=ROOT/i['parent']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or sha(Path(i['openroad']['path']))!=i['openroad']['sha256']):raise ValueError('Routing campaign context changed')
    pi,_=placement.bound(parent)
    if (out/'route.tcl').read_text()!=route_tcl(parent,out,pi['plan']):raise ValueError('Routing adapter cannot regenerate')
    return i,pi


def check(out,pi,required):
    def rows(name):return [line.split('\t') for line in (out/name).read_text().splitlines()]
    if Counter(map(tuple,rows('master_pins_before.tsv')))!=Counter(map(tuple,rows('master_pins_after.tsv'))):
        raise ValueError('Router did not restore exact master pin geometry/directions/supply types')
    cells=pi['plan']['cells'];wanted=Counter((c['name'],p,n) for c in cells for p,n in c['pins'].items())
    if Counter(map(tuple,rows('connections.tsv')))!=wanted:raise ValueError('Routed instance/native body connectivity changed')
    wanted={c['name']:[c['model'],'R0','FIRM',*[str(round(x*1000)) for x in pi['plan']['boxes'][c['name']]]] for c in cells}
    if {w[0]:w[1:] for w in rows('boxes.tsv')}!=wanted:raise ValueError('Routing moved or changed a native cell')
    wanted=Counter((p,'OUTPUT' if p=='OUT' else 'INOUT' if p in ('VPWR','VGND') else 'INPUT',
                    'POWER' if p=='VPWR' else 'GROUND' if p=='VGND' else 'SIGNAL',p) for p in pi['graph']['ports'])
    if Counter(map(tuple,rows('ports.tsv')))!=wanted:raise ValueError('Router public direction/supply types were not restored')
    nets={w[0]:w[1:] for w in rows('nets.tsv')}
    if set(nets)!=set(required)|{'IN','OUT'}:raise ValueError('Router lost or added a net')
    if any(nets[n][1]!='1' for n in required):raise ValueError('Missing detailed route for required signal/control/supply net')
    if any(nets[n][0]!=('POWER' if n=='VPWR' else 'GROUND' if n=='VGND' else 'SIGNAL') for n in nets):
        raise ValueError('Final native supply types differ')
    if any(nets[n][2]!='1' for n in ('VPWR','VGND','OUT')):raise ValueError('Fixed fine bus inventory was not restored')
    return dict(all_instance_and_body_connections_preserved=True,all_placements_preserved=True,
                public_native_supply_types_restored=True,all_master_pin_shapes_and_types_preserved=True,
                required_regular_wire_nets=len(required),all_required_nets_have_wire=True)


def run(out):
    i,pi=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial routing campaign')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n')
        with (out/'openroad.log').open('w') as log:
            p=subprocess.run([i['openroad']['path'],'-no_init','-exit',str(out/'route.tcl')],cwd=out,stdout=log,stderr=subprocess.STDOUT)
        result=None;error=None
        if p.returncode==0:
            try:result=check(out,pi,i['regular_wire_nets'])
            except ValueError as e:error=str(e)
        violations=re.findall(r'Number of violations\s*=\s*(\d+)',(out/'openroad.log').read_text())
        final=int(violations[-1]) if violations else None
        passed=p.returncode==0 and result is not None and final==0
        bound(out)
        report=dict(returncode=p.returncode,router_final_violations=final,connection_and_coverage_check=result,error=error,
                    route_bringup_passed=passed,whole_bank_gds_drc_passed=False,whole_bank_native_lvs_passed=False,
                    joint_rc_extracted=False,electrical_qualification_passed=False,qualified_phy=False)
        report['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
