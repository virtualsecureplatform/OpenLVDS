#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify reversible native router access to the regular regenerator-pair bank.

Corrects the retained v132 API failure: OpenDB calls this clearSpecial.
No route, candidate selection, joint RC or electrical admission is performed.
The temporary public pins represent exact existing metal, never added access pads.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import regular_regenerated_bank_physical_v273 as design

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def placement_bound(parent):
    import prepare_regular_regenerated_placement_v272 as placement
    return placement.bound(parent)

VERSION='regular-pair-m4-stages-fixed-bus-native-router-roundtrip-v274.1'
CONTEXT='regular_regenerated_routing_interface_v274'
TEMPLATE=ROOT/'scripts/prepare_isolated_fine_routing_interface_v240.tcl'


def contract(i):
    plan=i['plan'];cells={c['name']:c for c in plan['cells']}
    routes={r['net']:r for r in plan['fixed_routes']}
    if set(routes)!={'fine_node','VPWR','VGND'} or len(plan['fixed_routes'])!=3:
        raise ValueError('Require exactly three isolated fine fixed buses')
    buses=[]
    for net in ['fine_node','VPWR','VGND']:
        terms=[(f'u_fine_unit{k}','A' if net=='fine_node' else net) for k in range(31)]
        for name,pin in terms:
            if cells[name]['pins'][pin]!=net:raise ValueError('Fixed-bus terminal differs from native graph')
        route=routes[net]
        if route['layer']!='met3':raise ValueError('Unexpected fine fixed-bus layer')
        buses.append(dict(net=net,proxy='__fixed_bus_'+net,layer=route['layer'],rect=route['rect'],terminals=terms))
    selected=sorted((c['name'],pin) for c in plan['cells'] for pin,net in c['pins'].items() if net=='selected')
    roots=sorted((f'u_{prefix}{k}' if prefix=='root_parallel' else f'u_switch1_0_{k}','Z') for k in range(4) for prefix in ['root_parallel','switch'])
    if selected!=sorted([*roots,('u_fine_isolate','A')]):raise ValueError('Isolated selected path does not have eight roots and one driver')
    if cells['u_fine_isolate']['pins']['Y']!='fine_node':raise ValueError('Fine driver output changed')
    drivers={
        'u_fine_isolate':dict(A='selected',Y='fine_node'),
        'u_fine_regenerate0':dict(A='fine_node',Y='restored_b'),
        'u_fine_regenerate1':dict(A='restored_b',Y='OUT'),
    }
    for name,pins in drivers.items():
        cell=cells.get(name) or {}
        if cell.get('model')!=design.DRIVER or any(cell.get('pins',{}).get(p)!=net for p,net in {**pins,'VPWR':'VPWR','VGND':'VGND'}.items()):
            raise ValueError('Regular-pair native driver path or supplies changed')
        if any({layer for layer,rect in i['records'][design.DRIVER]['pins'][p]['shapes']}!={'met4'} for p in pins):
            raise ValueError('Require actual M4 data access on all three regular drivers')
    restored=sorted((c['name'],pin) for c in plan['cells'] for pin,net in c['pins'].items() if net=='restored_b')
    if restored!=[('u_fine_regenerate0','Y'),('u_fine_regenerate1','A')]:raise ValueError('Regular-pair intermediate net has wrong native endpoints')
    fine=sorted((c['name'],pin) for c in plan['cells'] for pin,net in c['pins'].items() if net=='fine_node')
    if fine!=sorted([*[(f'u_fine_unit{k}','A') for k in range(31)],('u_fine_isolate','Y'),('u_fine_regenerate0','A')]):
        raise ValueError('Regular-pair fine node has wrong native endpoints')
    if any(b['proxy'] in i['graph']['ports'] for b in buses):raise ValueError('Temporary port name collision')
    return dict(buses=buses,root_outputs=roots,m4_driver_data_connections=drivers,input_requires_regular_wire=True,
                regular_wire_nets=sorted(({n for c in plan['cells'] for n in c['pins'].values()}|set(i['graph']['ports']))-{'OUT'}))


def adapter(parent,out,c):
    adapt=[];restore=[]
    for b in c['buses']:
        net=b['net'];coords=' '.join(str(round(v*1000)) for v in b['rect'])
        adapt += [f'set net [$block findNet {net}]',
                  'if {[llength [$net getSWires]] != 1} {error "Unexpected fixed-bus wire inventory"}',
                  'foreach wire [$net getSWires] {odb::dbSWire_destroy $wire}',
                  f'set term [odb::dbBTerm_create $net {b["proxy"]}]', '$term setIoType INPUT', '$term setSigType SIGNAL',
                  'set pin [odb::dbBPin_create $term]', '$pin setPlacementStatus FIRM',
                  f'odb::dbBox_create $pin [[$db getTech] findLayer {b["layer"]}] {coords}']
        for name,pin in b['terminals']:
            adapt += [f'set term [[$block findInst {name}] findITerm {pin}]',
                      'if {[$term getNet] != $net} {error "Fixed-bus terminal has wrong native net"}',
                      'lappend disconnected [list $term $net]', '$term disconnect']
        restore += [f'odb::dbBTerm_destroy [$block findBTerm {b["proxy"]}]',
                    f'set net [$block findNet {net}]', 'set wire [odb::dbSWire_create $net ROUTED]',
                    f'odb::dbSBox_create $wire [[$db getTech] findLayer {b["layer"]}] {coords} STRIPE']
    return (TEMPLATE.read_text().replace('@PARENT@',str(parent)).replace('@OUT@',str(out))
            .replace('@ADAPT_BUSES@','\n'.join(adapt)).replace('@RESTORE_BUSES@','\n'.join(restore))
            .replace('@ROUTING_BODY@','# No routing in the interface preflight.'))


def prepare(parent):
    i=placement_bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['placement_feasibility_passed'] or r['placement_geometry']['drc_count']!='0'
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged clean balanced placement')
    c=contract(i)
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',*[parent/n for n in r['files']],Path(__file__),TEMPLATE]
    # Freeze every imported repository helper, including the placement binder.
    import sys
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profile='b2_regular_regenerated_p20n16',contract=c,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},openroad=i['openroad'],
                  scope='Native router-interface adaptation and exact restoration only; no routing or timing admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'interface.tcl').write_text(adapter(parent,out,c));return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];parent=ROOT/i['parent']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or sha(Path(i['openroad']['path']))!=i['openroad']['sha256']):raise ValueError('Router-interface inputs changed')
    pi=placement_bound(parent)
    if json.loads(json.dumps(contract(pi)))!=i['contract'] or (out/'interface.tcl').read_text()!=adapter(parent,out,i['contract']):
        raise ValueError('Router-interface contract cannot regenerate')
    return i,pi


def rows(out,name):return Counter(tuple(line.split('\t')) for line in (out/name).read_text().splitlines())


def verify(out,i,pi):
    for kind in ['connections','ports','boxes','masters','nets','buses']:
        if rows(out,'before_'+kind+'.tsv')!=rows(out,'after_'+kind+'.tsv'):
            raise ValueError('Native router-interface roundtrip changed '+kind)
    wanted=Counter((c['name'],pin,net) for c in pi['plan']['cells'] for pin,net in c['pins'].items())
    if rows(out,'before_connections.tsv')!=wanted:raise ValueError('Native input graph differs from canonical placement')
    removed={(name,pin):b['net'] for b in i['contract']['buses'] for name,pin in b['terminals']}
    routing={tuple(w[:2]):w[2] for w in rows(out,'adapted_connections.tsv')}
    for key,net in {(a,b):n for a,b,n in wanted}.items():
        if routing[key] not in (['NULL'] if key in removed else [net,'NULL']):
            raise ValueError('Routing interface changed a retained terminal net')
    # Only nonrouting native body pins may join the 93 fixed-rail disconnections.
    shapes={tuple(w[:2]):w[2] for w in rows(out,'terminal_routing.tsv')}
    if any(routing[k]=='NULL' and k not in removed and shapes[k]!='0' for k in routing):
        raise ValueError('Routing interface disconnected a live signal/control terminal')
    for name,pin in i['contract']['root_outputs']:
        if routing[name,pin]!='selected':raise ValueError('Native root output missing from routing interface')
    if routing.get(('u_fine_isolate','A'))!='selected' or routing.get(('u_fine_isolate','Y'))!='fine_node':
        raise ValueError('M4 fine isolation driver disconnected from router interface')
    for name,pins in i['contract']['m4_driver_data_connections'].items():
        for pin,net in pins.items():
            if routing.get((name,pin))!=net:raise ValueError('M4 regular-pair stage disconnected or bypassed in router interface')
    adapted_ports=rows(out,'adapted_ports.tsv')
    for b in i['contract']['buses']:
        if (b['proxy'],'INPUT','SIGNAL',b['net']) not in adapted_ports:raise ValueError('Missing fixed-metal router port')
    if len(adapted_ports)!=len(pi['graph']['ports'])+3:raise ValueError('Unexpected temporary public interface')
    proxies=rows(out,'proxy_shapes.tsv')
    wanted_shapes=Counter((b['proxy'],b['layer'],*[str(round(v*1000)) for v in b['rect']]) for b in i['contract']['buses'])
    if proxies!=wanted_shapes:raise ValueError('Temporary port invents or misses existing fixed metal')
    if rows(out,'adapted_buses.tsv'):raise ValueError('Fixed metal must have one temporary representation')
    return dict(exact_native_roundtrip_passed=True,all_eight_root_outputs_retained=True,m4_fine_driver_connections_retained=True,
                all_three_m4_driver_paths_retained=True,all_signal_and_control_connections_retained=True,existing_fixed_metal_proxy_shapes_verified=True,
                fixed_bus_terminal_count=len(removed),temporary_ports=3,instances=len(pi['plan']['cells']),
                routed=False,timing_candidate_admitted=False,qualified_phy=False)


def run(out):
    i,pi=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial interface check')
        (out/'state.json').write_text('{"status":"checking","qualified_phy":false}\n')
        with (out/'openroad.log').open('w') as log:
            p=subprocess.run([i['openroad']['path'],'-no_init','-exit',str(out/'interface.tcl')],cwd=out,stdout=log,stderr=subprocess.STDOUT)
        result=None;error=None
        if p.returncode==0:
            try:result=verify(out,i,pi)
            except ValueError as e:error=str(e)
        bound(out);passed=result is not None
        report=dict(returncode=p.returncode,result=result,error=error,interface_preflight_passed=passed,routed=False,joint_rc_extracted=False,qualified_phy=False)
        report['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
