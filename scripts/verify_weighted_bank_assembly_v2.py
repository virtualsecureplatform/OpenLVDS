#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reload the saved full-bank OpenDB and compare it with the native SPICE hierarchy."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import assemble_weighted_bank_v2 as assembly

ROOT=assembly.ROOT
sha=assembly.sha
VERSION='independent-full-weighted-bank-opendb-reload-verification-v2.1'


def connections(text,orders):
    defs=assembly.bank.native.definitions(text)
    if len(defs)!=1:raise ValueError('Require the single complete physical bank top')
    top,(ports,body)=next(iter(defs.items()));seen=set();result=[];models={}
    for w in body:
        if w[0][0]!='X' or w[0][1:] in seen:raise ValueError('Duplicate or non-instance bank statement')
        name=w[0][1:];seen.add(name);model=w[-1]
        if model not in orders or len(w[1:-1])!=len(orders[model]):raise ValueError('Unknown bank model or wrong pin count')
        models[name]=model;result += [(name,p,n) for p,n in zip(orders[model],w[1:-1])]
    return top,ports,models,Counter(result)


def verify(parent):
    m=assembly.bound(parent);i=m['identity'];prior=json.loads((parent/'summary.json').read_text())
    if not prior['passed'] or not prior['native_network_equivalence_passed']:raise ValueError('Require complete passing bank assembly')
    pm=assembly.candidate.bound(ROOT/i['parent']);pi=pm['identity']
    modules,orders,_,_=assembly.candidate.libraries(ROOT/pi['compound'],ROOT/pi['guard'],ROOT/pi['fine_cells'],ROOT/pi['clock'],Path(pi['source_library']))
    orders[assembly.shared.NAME]=['NODE','VSS']
    if orders!=i['orders']:raise ValueError('Native model interfaces changed')
    source=(parent/'bank.spice').read_text();library=modules['cells.spice']+(ROOT/i['shared']/(assembly.shared.NAME+'.sch.spice')).read_text()
    original=assembly.bank.leaves(library+modules['guarded.spice'],assembly.bank.candidate.NAME)
    physical=assembly.bank.leaves(library+source,assembly.bank.NAME)
    if physical!=original or hashlib.sha256(json.dumps(sorted(physical.items())).encode()).hexdigest()!=i['flattened_network_sha256']:
        raise ValueError('Full native leaf network changed')
    top,ports,models,expected=connections(source,orders)
    if top!=assembly.bank.NAME or ports!=assembly.bank.PORTS or len(models)!=94 or len(expected)!=473:
        raise ValueError('Incomplete physical bank source')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json',*prior['files']]]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  code={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))},openroad=i['openroad'],openroad_sha256=i['openroad_sha256'])
    out=ROOT/'build/diagnostics/weighted_bank_assembly_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    lines=[f'read_db {{{parent/"macro_preflight.odb"}}}','set db [ord::get_db]','set block [[$db getChip] getBlock]',
           f'set f [open {{{out/"header.tsv"}}} w]','set box [$block getDieArea]',
           'puts $f "[$block getName]\t[$box xMin]\t[$box yMin]\t[$box xMax]\t[$box yMax]"','close $f',
           f'set f [open {{{out/"connections.tsv"}}} w]',
           'foreach inst [$block getInsts] {foreach term [$inst getITerms] {set net [$term getNet]',
           'if {$net == "NULL"} {error "Unconnected serialized terminal"}',
           'puts $f "[$inst getName]\t[[$term getMTerm] getName]\t[$net getName]"','}}','close $f',
           f'set f [open {{{out/"instances.tsv"}}} w]',
           'foreach inst [$block getInsts] {set b [$inst getBBox]',
           'puts $f "[$inst getName]\t[[$inst getMaster] getName]\t[$inst getPlacementStatus]\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"','}','close $f',
           f'set f [open {{{out/"public.tsv"}}} w]',
           'foreach term [$block getBTerms] {puts $f "[$term getName]\t[$term getIoType]\t[$term getSigType]\t[[$term getNet] getName]"}','close $f',
           f'set f [open {{{out/"pins.tsv"}}} w]']
    for name in i['macros']:
        lines += [f'set master [$db findMaster {name}]','foreach term [$master getMTerms] {set layers {}',
                  'foreach pin [$term getMPins] {foreach shape [$pin getGeometry] {lappend layers [[$shape getTechLayer] getName]}}',
                  f'puts $f "{name}\t[$term getName]\t[$term getIoType]\t[$term getSigType]\t[join [lsort -unique $layers] ,]"','}']
    lines += ['close $f','exit'];(out/'readback.tcl').write_text('\n'.join(lines)+'\n')
    with (out/'openroad.log').open('w') as log:
        process=subprocess.run([i['openroad'],'-no_init','-exit',str(out/'readback.tcl')],cwd=out,stdout=log,stderr=subprocess.STDOUT)
    def rows(name):
        path=out/name
        return [line.split('\t') for line in path.read_text().splitlines()] if path.exists() else []
    errors=[]
    if Counter(map(tuple,rows('connections.tsv')))!=expected:errors.append('Serialized connectivity differs from source SPICE')
    header=rows('header.tsv');wanted=[top,*[str(round(v*1000)) for v in i['die']]]
    if header!=[wanted]:errors.append('Serialized die or top changed')
    observed={};boxes={}
    for name,model,status,*coords in rows('instances.tsv'):
        if name in observed:errors.append('Duplicate serialized instance')
        observed[name]=model
        if name in i['placements']:
            if status!='FIRM':errors.append('Macro placement status changed: '+name)
            box=[int(v)/1000 for v in coords];boxes[name]=box
            p=i['placements'][name]['location'];cell=assembly.geometry.lef_cell(Path(i['macros'][model]['lef'][0]).read_text(),model)
            wanted_box=[*p,p[0]+cell['width'],p[1]+cell['height']]
            if any(abs(a-b)>.001 for a,b in zip(box,wanted_box)):errors.append('Serialized macro position/size changed: '+name)
    if observed!=models or set(boxes)!=set(i['placements']):errors.append('Serialized instance/model coverage changed')
    try:assembly.no_overlaps(boxes,i['die'])
    except ValueError as exc:errors.append(str(exc))
    public={(p,'OUTPUT' if p=='OUT' else 'INOUT' if p in ['VPWR','VGND'] else 'INPUT',
             'POWER' if p=='VPWR' else 'GROUND' if p=='VGND' else 'SIGNAL',p) for p in ports}
    if Counter(map(tuple,rows('public.tsv')))!=Counter(public):errors.append('Serialized public interface changed')
    pins={(name,p,v['direction'],v['use'],v['layer']) for name,macro in i['macros'].items() for p,v in macro['pins'].items()}
    if Counter(map(tuple,rows('pins.tsv')))!=Counter(pins):errors.append('Serialized macro access changed')
    assembly.bound(parent)
    passed=process.returncode==0 and not errors
    result=dict(passed=passed,returncode=process.returncode,errors=errors,instances=len(models),macro_instances=len(boxes),
                connected_iterms=sum(expected.values()),public_ports=len(ports),native_network_equivalence_passed=True,
                qualified_phy=False,electrical_qualification_passed=False,route_complete=False,
                scope='Independent source leaf comparison and fresh serialized OpenDB readback of exact native bank connectivity/interfaces/macro placement; no routed-bank DRC/LVS/RC, timing or PHY admission')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='verified',passed=passed,qualified_phy=False))+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(verify(a.artifact.resolve()),flush=True)
