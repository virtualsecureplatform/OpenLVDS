#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Assemble both2 placement, physical taps and fixed fine data/power buses."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import klayout.db as db
import bank_floorplan_v49 as floorplan
import layout
import verify_bank_cell_registry_v48 as audit

ROOT=layout.ROOT
sha=audit.sha
VERSION='both2-tapped-control-rows-short-zero-path-placement-v49.1'
CONTEXT='tg_bank_floorplan_v49'


def inputs(evidence):
    ai=audit.bound(evidence);parent=ROOT/ai['parent'];pi=audit.producer.bound(parent)
    report=json.loads((parent/'summary.json').read_text())
    if (len(report['custom_native_qualification'])!=5 or
            not all(q['physical']['passed'] and q['native_dimensions_and_junctions_preserved'] for q in report['custom_native_qualification'].values())):
        raise ValueError('Require all five custom native physical qualifications')
    graph=json.loads((ROOT/pi['graph_parent']/'manifest.json').read_text())['identity']['graph']
    return parent,pi,graph,report['cells']


def opendb(out,pi,graph,plan):
    parent=ROOT/pi['_parent']
    lines=[f'read_lef {{{pi["tech_lef"]}}}',f'read_lef {{{parent/"library.lef"}}}',
           'set db [ord::get_db]', 'if {[[$db getTech] getDbUnitsPerMicron] != 1000} {error "Changed database units"}',
           'set chip [odb::dbChip_create $db [$db getTech]]',f'set block [odb::dbBlock_create $chip {graph["top"]}]',
           '$block setDefUnits 1000',
           f'$block setDieArea [odb::Rect bank_die 0 0 {round(plan["die"][2]*1000)} {round(plan["die"][3]*1000)}]',
           f'$block setCoreArea [odb::Rect bank_core 0 0 {round(plan["die"][2]*1000)} {round(plan["die"][3]*1000)}]']
    for port in graph['ports']:
        io='OUTPUT' if port=='OUT' else 'INOUT' if port in ('VPWR','VGND') else 'INPUT'
        sig='POWER' if port=='VPWR' else 'GROUND' if port=='VGND' else 'SIGNAL'
        lines += [f'set net [odb::dbNet_create $block {port}]',f'$net setSigType {sig}',
                  f'set term [odb::dbBTerm_create $net {port}]',f'$term setIoType {io}',f'$term setSigType {sig}']
        pin=plan['ports'][port];coords=' '.join(str(round(x*1000)) for x in pin['rect'])
        lines += ['set pin [odb::dbBPin_create $term]','$pin setPlacementStatus FIRM',
                  f'odb::dbBox_create $pin [[$db getTech] findLayer {pin["layer"]}] {coords}']
    for c in plan['cells']:
        name=c['name'];x,y=plan['placements'][name]
        lines += [f'set master [$db findMaster {c["model"]}]', 'if {$master == "NULL"} {error "Missing physical master"}',
                  f'set inst [odb::dbInst_create $block $master {name}]',f'$inst setLocation {round(x*1000)} {round(y*1000)}',
                  '$inst setOrient R0','$inst setPlacementStatus FIRM']
        for pin,net in c['pins'].items():
            lines += [f'set term [$inst findITerm {pin}]', 'if {$term == "NULL"} {error "Missing physical terminal"}',
                      f'set net [$block findNet {net}]',f'if {{$net == "NULL"}} {{set net [odb::dbNet_create $block {net}]}}','$term connect $net']
    # Search actual tech-library sites; no invented row lattice.
    lines += ['set site NULL','foreach lib [$db getLibs] {set s [$lib findSite unithd]; if {$s != "NULL"} {set site $s}}',
              'if {$site == "NULL"} {error "Missing HD row site"}']
    # Retain a complete placement lattice around fixed macros. An explicitly
    # initialized core is also required by OpenDP for a directly created DB.
    # Rows are placement metadata, not manufactured well geometry;
    # only the explicit tapped groups above contain standard-cell instances.
    for k in range(round(plan['die'][3]/floorplan.ROW)):
        lines += [f'odb::dbRow_create $block row_{k} $site 0 {round(k*floorplan.ROW*1000)} R0 HORIZONTAL {round(plan["die"][2]/floorplan.SITE)} 460']
    for route in plan['fixed_routes']:
        coords=' '.join(str(round(x*1000)) for x in route['rect'])
        lines += [f'set net [$block findNet {route["net"]}]','set wire [odb::dbSWire_create $net ROUTED]',
                  f'odb::dbSBox_create $wire [[$db getTech] findLayer {route["layer"]}] {coords} STRIPE']
    lines += [f'set f [open {{{out/"connections.tsv"}}} w]',f'set g [open {{{out/"boxes.tsv"}}} w]',
              'foreach inst [$block getInsts] {',
              'set b [$inst getBBox]',
              'puts $g "[$inst getName]\\t[[$inst getMaster] getName]\\t[$inst getOrient]\\t[$inst getPlacementStatus]\\t[$b xMin]\\t[$b yMin]\\t[$b xMax]\\t[$b yMax]"',
              'foreach term [$inst getITerms] {set n [$term getNet]; if {$n == "NULL"} {error "Unconnected logical terminal"}',
              'puts $f "[$inst getName]\\t[[$term getMTerm] getName]\\t[$n getName]"','}}','close $f','close $g',
              f'set f [open {{{out/"ports.tsv"}}} w]',
              'foreach p [$block getBTerms] {puts $f "[$p getName]\\t[$p getIoType]\\t[$p getSigType]\\t[[$p getNet] getName]"}',
              'close $f','check_placement -verbose',f'write_db {{{out/"placed.odb"}}}',f'write_def {{{out/"placed.def"}}}','exit']
    (out/'placement.tcl').write_text('\n'.join(lines)+'\n')
    p=subprocess.run([pi['openroad']['path'],'-no_init','-exit',str(out/'placement.tcl')],cwd=out,capture_output=True,text=True)
    (out/'openroad.log').write_text(p.stdout+p.stderr);p.check_returncode()
    wanted=Counter((c['name'],pin,net) for c in plan['cells'] for pin,net in c['pins'].items())
    actual=Counter(tuple(line.split('\t')) for line in (out/'connections.tsv').read_text().splitlines())
    if actual!=wanted:raise ValueError('Placed OpenDB connectivity differs from full physical graph')
    actual={w[0]:w[1:] for line in (out/'boxes.tsv').read_text().splitlines() if (w:=line.split('\t'))}
    expected={c['name']:[c['model'],'R0','FIRM',*[str(round(x*1000)) for x in plan['boxes'][c['name']]]] for c in plan['cells']}
    if actual!=expected:raise ValueError('Actual OpenDB placements or master dimensions differ')
    wanted=Counter((p,'OUTPUT' if p=='OUT' else 'INOUT' if p in ('VPWR','VGND') else 'INPUT',
                    'POWER' if p=='VPWR' else 'GROUND' if p=='VGND' else 'SIGNAL',p) for p in graph['ports'])
    actual=Counter(tuple(line.split('\t')) for line in (out/'ports.tsv').read_text().splitlines())
    if actual!=wanted:raise ValueError('Public placed interface differs from canonical physical graph')
    return dict(all_instance_connections_verified=True,all_placements_and_sizes_verified=True,public_interface_verified=True,
                total_instances=len(plan['cells']),tapped_rows=len(plan['tapped_groups']))


def gds(out,parent,graph,plan):
    lib=db.Layout();lib.read(str(parent/'library.gds'));top=lib.create_cell(graph['top'])
    for c in plan['cells']:
        master=lib.cell(c['model']);x,y=plan['placements'][c['name']]
        if master is None:raise ValueError('Missing registered GDS master')
        inst=top.insert(db.CellInstArray(master.cell_index(),db.Trans(round(x/lib.dbu),round(y/lib.dbu))))
        inst.set_property(61,c['name'])
    for name,pin in plan['ports'].items():
        layer=audit.geometry.ROUTING[pin['layer']]
        top.shapes(lib.layer(*layer)).insert(db.Box(*[round(x/lib.dbu) for x in pin['rect']]))
        x0,y0,x1,y1=pin['rect']
        top.shapes(lib.layer(layer[0],5)).insert(db.Text(name,db.Trans(round((x0+x1)/2/lib.dbu),round((y0+y1)/2/lib.dbu))))
    for route in plan['fixed_routes']:
        top.shapes(lib.layer(*audit.geometry.ROUTING[route['layer']])).insert(db.Box(*[round(x/lib.dbu) for x in route['rect']]))
    path=out/(graph['top']+'.gds');options=db.SaveLayoutOptions();options.select_cell(top.cell_index());lib.write(str(path),options)
    # Verify actual stored instance model/origin multiplicities, not plan alone.
    fresh=db.Layout();fresh.read(str(path));root=fresh.cell(graph['top'])
    actual=Counter((inst.cell.name,inst.trans.disp.x,inst.trans.disp.y) for inst in root.each_inst())
    expected=Counter((c['model'],round(plan['placements'][c['name']][0]/lib.dbu),round(plan['placements'][c['name']][1]/lib.dbu)) for c in plan['cells'])
    if actual!=expected:raise ValueError('Stored assembled GDS instance placements changed')
    return path


def fixed_bus_audit(path,graph,plan,records):
    lib=db.Layout();lib.read(str(path));top=lib.cell(graph['top'])
    metal=audit.region(lib,top,(70,20));result={}
    for route in plan['fixed_routes']:
        seed=db.Region(db.Box(*[round(x/lib.dbu) for x in route['rect']]))
        connected=metal.interacting(seed).merged()
        if connected.count()!=1:raise ValueError('Fixed fine bus is not one actual metal component')
        touched=[]
        for c in plan['cells']:
            dx,dy=[round(x/lib.dbu) for x in plan['placements'][c['name']]]
            for pin,r in records[c['model']]['pins'].items():
                for layer,rect in r['shapes']:
                    if layer!='met3':continue
                    shape=db.Region(db.Box(*[round(x/lib.dbu) for x in rect]).transformed(db.Trans(dx,dy)))
                    if (shape&connected).is_empty():continue
                    if c['pins'][pin]!=route['net']:raise ValueError('Fixed bus shorts another named native terminal')
                    if not (shape-connected).is_empty():raise ValueError('Fixed bus touches only a fragment of a public rail')
                    touched.append((c['name'],pin))
        required={(f'u_fine_unit{k}','A' if route['net']=='OUT' else route['net']) for k in range(31)}
        if route['net']=='OUT':required.add(('u_fine_driver','Y'))
        if not required<=set(touched):raise ValueError('Fixed fine bus misses native data or supply terminal')
        result[route['net']]=dict(one_physical_metal_component=True,required_native_rails_connected=len(required),
                                  other_named_nets_shorted=False)
    return result


def drc(out,path,top):
    folder=out/'drc';folder.mkdir();lib=db.Layout();lib.read(str(path))
    commands=['gds readonly false',f'gds read {{{path}}}']
    for cell in lib.each_cell():commands += [f'load {cell.name}',f'save {cell.name}']
    commands += [f'load {top}',f'flatten {top}_flat',f'load {top}_flat','select top cell',
                 'box values -100um -100um 10000um 10000um','drc euclidean on','drc on','drc check','drc catchup',
                 'set f [open drc.txt w]','puts $f [drc listall why]','close $f',
                 'set f [open count.txt w]','puts $f [drc listall count total]','close $f']
    layout.invoke_magic(folder,'\n'.join(commands),'placement_drc')
    count=(folder/'count.txt').read_text().strip()
    return dict(drc_count=count,placement_and_fixed_bus_drc_passed=count=='0',qualified_phy=False)


def svg(out,plan):
    w,h=plan['die'][2:];rows=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-3 -8 {w+6} {h+12}">',
        '<rect x="-3" y="-8" width="100%" height="100%" fill="white"/>',
        '<text x="0" y="-3" font-size="3">Both2 placement: 156 functional cells + 86 taps + 86 fillers. Unrouted.</text>']
    for c in plan['cells']:
        name=c['name'];x,y,x1,y1=plan['boxes'][name]
        color='#e49b51' if name in plan['critical_chain'] else '#79b6ce' if c['model']==floorplan.FINE else '#b6c88d' if c['model'].startswith(floorplan.SC) else '#d7c3e2'
        rows += [f'<rect x="{x}" y="{h-y1}" width="{x1-x}" height="{y1-y}" fill="{color}" stroke="#333" stroke-width=".08"><title>{name}: {c["model"]}</title></rect>']
    for route in plan['fixed_routes']:
        x,y,x1,y1=route['rect'];color='#c43f36' if route['net']=='VPWR' else '#444' if route['net']=='VGND' else '#007f61'
        rows += [f'<rect x="{x}" y="{h-y1}" width="{x1-x}" height="{y1-y}" fill="{color}"><title>Fixed {route["net"]} metal3 bus</title></rect>']
    rows += ['</svg>'];(out/'floorplan.svg').write_text('\n'.join(rows)+'\n')


def prepare(evidence):
    parent,pi,graph,records=inputs(evidence);plan=floorplan.derive(graph,records)
    paths=[evidence/'manifest.json',evidence/'summary.json',parent/'manifest.json',parent/'summary.json']
    for folder in (evidence,parent):
        r=json.loads((folder/'summary.json').read_text());paths += [folder/n for n in r['files']]
    code=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                 if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),parent=str(parent.relative_to(ROOT)),graph=graph,plan=plan,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={str(p.relative_to(ROOT)):sha(p) for p in code})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())):raise ValueError('Bank floorplan context changed')
    parent,pi,g,r=inputs(ROOT/i['evidence'])
    if graph_canonical(g)!=i['graph'] or graph_canonical(floorplan.derive(g,r))!=i['plan']:raise ValueError('Floorplan cannot regenerate')
    return i,dict(pi,_parent=str(parent.relative_to(ROOT)))


def graph_canonical(value):return json.loads(json.dumps(value,sort_keys=True))


def run(out):
    i,pi=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial floorplan experiment')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        plan=i['plan'];parent=ROOT/i['parent'];graph=i['graph']
        records=json.loads((parent/'summary.json').read_text())['cells']
        observed=opendb(out,pi,graph,plan);path=gds(out,parent,graph,plan)
        buses=fixed_bus_audit(path,graph,plan,records);check=drc(out,path,graph['top']);svg(out,plan)
        bound(out)
        report=dict(opendb=observed,fixed_buses=buses,placement_geometry=check,placement_passed=check['placement_and_fixed_bus_drc_passed'],
                    functional_instances=156,physical_taps=86,physical_fillers=86,
                    well_tap_connection_requires_routed_lvs=True,route_complete=False,io_pins_placed=True,
                    whole_bank_lvs_passed=False,electrical_qualification_passed=False,qualified_phy=False)
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='complete',passed=report['placement_passed'],qualified_phy=False))+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
