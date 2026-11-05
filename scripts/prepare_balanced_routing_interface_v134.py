#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify reversible router access to existing balanced-bank fixed metal buses.

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
import prepare_balanced_placement_v129 as placement

ROOT=placement.ROOT
sha=placement.sha
VERSION='balanced-fixed-bus-router-interface-native-roundtrip-v134.1'
CONTEXT='balanced_routing_interface_v134'
TEMPLATE=Path(__file__).with_suffix('.tcl')


def contract(i):
    plan=i['plan'];cells={c['name']:c for c in plan['cells']}
    routes={r['net']:r for r in plan['fixed_routes']}
    if set(routes)!={'selected','VPWR','VGND'} or len(plan['fixed_routes'])!=3:
        raise ValueError('Require exactly three qualified fixed buses')
    buses=[]
    for net in ['selected','VPWR','VGND']:
        terms=[(f'u_fine_unit{k}','A' if net=='selected' else net) for k in range(31)]
        if net=='selected':terms.append(('u_fine_compound','A'))
        for name,pin in terms:
            if cells[name]['pins'][pin]!=net:raise ValueError('Fixed-bus terminal differs from native graph')
        route=routes[net]
        if route['layer']!='met3':raise ValueError('Unexpected fixed-bus layer')
        buses.append(dict(net=net,proxy='__fixed_bus_'+net,layer=route['layer'],rect=route['rect'],terminals=terms))
    roots=sorted((c['name'],pin) for c in plan['cells'] for pin,net in c['pins'].items()
                 if net=='selected' and (c['name'],pin) not in set(buses[0]['terminals']))
    wanted=sorted((f'u_{prefix}{k}' if prefix=='root_parallel' else f'u_switch1_0_{k}','Z') for k in range(4) for prefix in ['root_parallel','switch'])
    if roots!=wanted:raise ValueError('Require all eight native root outputs for regular routing')
    if any(b['proxy'] in i['graph']['ports'] for b in buses):raise ValueError('Temporary port name collision')
    return dict(buses=buses,root_outputs=roots,input_requires_regular_wire=True,
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
    i=placement.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['placement_feasibility_passed'] or r['placement_geometry']['drc_count']!='0'
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged clean balanced placement')
    c=contract(i)
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',*[parent/n for n in r['files']],Path(__file__),TEMPLATE]
    # Freeze every imported repository helper, including the placement binder.
    import sys
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profile=i['profile'],contract=c,
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
    pi=placement.bound(parent)
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
    # Only nonrouting native body pins may join the 94 fixed-rail disconnections.
    shapes={tuple(w[:2]):w[2] for w in rows(out,'terminal_routing.tsv')}
    if any(routing[k]=='NULL' and k not in removed and shapes[k]!='0' for k in routing):
        raise ValueError('Routing interface disconnected a live signal/control terminal')
    for name,pin in i['contract']['root_outputs']:
        if routing[name,pin]!='selected':raise ValueError('Native root output missing from routing interface')
    adapted_ports=rows(out,'adapted_ports.tsv')
    for b in i['contract']['buses']:
        if (b['proxy'],'INPUT','SIGNAL',b['net']) not in adapted_ports:raise ValueError('Missing fixed-metal router port')
    if len(adapted_ports)!=len(pi['graph']['ports'])+3:raise ValueError('Unexpected temporary public interface')
    proxies=rows(out,'proxy_shapes.tsv')
    wanted_shapes=Counter((b['proxy'],b['layer'],*[str(round(v*1000)) for v in b['rect']]) for b in i['contract']['buses'])
    if proxies!=wanted_shapes:raise ValueError('Temporary port invents or misses existing fixed metal')
    if rows(out,'adapted_buses.tsv'):raise ValueError('Fixed metal must have one temporary representation')
    return dict(exact_native_roundtrip_passed=True,all_eight_root_outputs_retained=True,
                all_signal_and_control_connections_retained=True,existing_fixed_metal_proxy_shapes_verified=True,
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
