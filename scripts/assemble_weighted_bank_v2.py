#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check the full candidate's exact physical hierarchy and macro placement in OpenDB."""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import weighted_bank_physical_v2 as bank
import probe_weighted_direct_v3 as candidate
import build_compound_drivers_v3 as geometry
import build_mim_base_4x4_v3 as shared
from assemble_dcdl_bank_inputs_v3 import no_overlaps

ROOT=geometry.ROOT
sha=geometry.sha
VERSION='full-native-weighted-bank-opendb-assembly-v2.1'


def locations(macros):
    cells=bank.instances();core=[c for c in cells if re.fullmatch(r'(forward|turn|pass|merge)\d+',c['name'])]
    sizes={name:geometry.lef_cell(Path(m['lef'][0]).read_text(),name) for name,m in macros.items()}
    pitch=math.ceil((max(sizes[c['model']]['height'] for c in core)+10)*100)/100
    columns={};x=10.
    for role in ['forward','turn','pass','merge']:
        columns[role]=x
        x+=max(sizes[c['model']]['width'] for c in core if c['name'].startswith(role))+10.
    fine_x=x+20.;fine_columns={};x=fine_x
    for role in ['fine_buffer','fine_inverse','fine']:
        fine_columns[role]=x
        selected=[c for c in cells if re.fullmatch(role+r'\d+',c['name'])]
        x+=max(sizes[c['model']]['width'] for c in selected)+10.
    fine_pitch=math.ceil((max(sizes[c['model']]['height'] for c in cells if c['name'].startswith('fine'))+10)*100)/100
    result={}
    for cell in cells:
        if cell['model'] not in macros:continue
        name=cell['name'];match=re.fullmatch(r'(forward|turn|pass|merge)(\d+)',name)
        if match:point=[columns[match[1]],10.+int(match[2])*pitch]
        elif name=='shared_base':point=[fine_x,10.+5*fine_pitch]
        else:
            match=re.fullmatch(r'(fine_buffer|fine_inverse|fine)(\d+)',name)
            if match is None:raise ValueError('Unknown physical bank macro placement')
            point=[fine_columns[match[1]],10.+int(match[2])*fine_pitch]
        result[name]=dict(location=point,orientation='N')
    boxes={c['name']:[*result[c['name']]['location'],
             result[c['name']]['location'][0]+sizes[c['model']]['width'],
             result[c['name']]['location'][1]+sizes[c['model']]['height']]
           for c in cells if c['name'] in result}
    die=[0.,0.,math.ceil(max(b[2] for b in boxes.values())+10),math.ceil(max(b[3] for b in boxes.values())+10)]
    no_overlaps(boxes,die);return result,die


def build(parent,base):
    m=candidate.bound(parent);i=m['identity'];cells=bank.instances()
    modules,orders,_,files=candidate.libraries(ROOT/i['compound'],ROOT/i['guard'],ROOT/i['fine_cells'],ROOT/i['clock'],Path(i['source_library']))
    if any((parent/n).read_text()!=text for n,text in modules.items()):raise ValueError('Bank source library regeneration changed')
    used={c['model'] for c in cells};macros={}
    for receipt in [ROOT/i[n] for n in ['compound','guard','fine_cells','clock']]:
        info=json.loads((receipt/'manifest.json').read_text())['identity'];physical=ROOT/info['parent']
        report=json.loads((physical/'summary.json').read_text())
        for row in report['rows']:
            name=row['macro']
            if name not in used:continue
            if name in macros or row['drc_count']!='0' or not row['lvs_passed'] or not row['passed']:raise ValueError('Missing/duplicate clean physical macro')
            folder=physical/name
            if sha(folder/(name+'.gds'))!=row['gds_sha256'] or sha(folder/(name+'.lef'))!=row['lef_sha256']:raise ValueError('Physical macro output changed')
            macros[name]=dict(gds=[str(folder/(name+'.gds'))],lef=[str(folder/(name+'.lef'))],spice=[str(folder/(name+'.sch.spice'))],pins=row['integration_pins'],instances={})
            files += [folder/n for n in ['summary.json',name+'.gds',name+'.lef',name+'.sch.spice',name+'.lvs.log',name+'.drc_count.txt']]
    shared.bound(base);br=json.loads((base/'summary.json').read_text());name=shared.NAME
    if (not br['passed'] or br['drc_count']!='0' or not br['lvs_passed']
        or sha(base/(name+'.gds'))!=br['gds_sha256'] or sha(base/(name+'.lef'))!=br['lef_sha256']):raise ValueError('Shared physical MIM changed')
    macros[name]=dict(gds=[str(base/(name+'.gds'))],lef=[str(base/(name+'.lef'))],spice=[str(base/(name+'.sch.spice'))],pins=br['integration_pins'],instances={})
    files += [base/n for n in ['manifest.json','summary.json','state.json',name+'.gds',name+'.lef',name+'.sch.spice',name+'.lvs.log',name+'.drc_count.txt']]
    orders=dict(orders);orders[name]=['NODE','VSS'];source=bank.spice(orders)
    library=modules['cells.spice']+(base/(name+'.sch.spice')).read_text()
    original=bank.leaves(library+modules['guarded.spice'],bank.candidate.NAME)
    physical=bank.leaves(library+source,bank.NAME)
    if physical!=original:raise ValueError('Physical hierarchy changed native R/C/MOS/MIM connectivity or dimensions')
    if len(macros)!=11:raise ValueError('Require all eleven exact physical macro types')
    places,die=locations(macros)
    for c in cells:
        if c['model'] in macros:macros[c['model']]['instances'][c['name']]=places[c['name']]
    if len(places)!=78:raise ValueError('Require all 78 physical macro instances')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd'
    tech=pdk/'techlef/sky130_fd_sc_hd__nom.tlef';lef=pdk/'lef/sky130_fd_sc_hd.lef';tool=shutil.which('openroad')
    if tool is None:raise ValueError('Use the pinned physical-tools environment')
    files += [parent/'manifest.json',*[parent/n for n in m['libraries']],*[ROOT/n for n in i['inputs']],
              Path(__file__),Path(bank.__file__),Path(candidate.__file__),Path(geometry.__file__),Path(shared.__file__),ROOT/'scripts/assemble_dcdl_bank_inputs_v3.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),shared=str(base.relative_to(ROOT)),
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in files},pdk_files={str(p):sha(p) for p in [tech,lef,pdk/'gds/sky130_fd_sc_hd.gds',pdk/'spice/sky130_fd_sc_hd.spice']},
                  openroad=tool,openroad_sha256=sha(Path(tool)),macros=macros,placements=places,die=die,orders=orders,
                  flattened_network_sha256=hashlib.sha256(json.dumps(sorted(physical.items())).encode()).hexdigest())
    out=ROOT/'build/diagnostics/weighted_bank_assembly_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'bank.spice').write_text(source);(out/'bank.v').write_text(bank.verilog(orders))
    (out/'state.json').write_text('{"status":"checking_opendb","qualified_phy":false}\n')
    lines=[f'read_lef {{{tech}}}',f'read_lef {{{lef}}}']+[f'read_lef {{{v["lef"][0]}}}' for v in macros.values()]
    lines += ['set db [ord::get_db]','if {[[$db getTech] getDbUnitsPerMicron] != 1000} {error "Unexpected database units"}',
              'set chip [odb::dbChip_create $db [$db getTech]]',f'set block [odb::dbBlock_create $chip {bank.NAME}]',
              f'$block setDieArea [odb::Rect bank_die 0 0 {int(die[2]*1000)} {int(die[3]*1000)}]']
    for port in bank.PORTS:
        io='OUTPUT' if port=='OUT' else 'INOUT' if port in ['VPWR','VGND'] else 'INPUT'
        sig='POWER' if port=='VPWR' else 'GROUND' if port=='VGND' else 'SIGNAL'
        lines += [f'set net [odb::dbNet_create $block {port}]',f'$net setSigType {sig}',f'set term [odb::dbBTerm_create $net {port}]',f'$term setIoType {io}',f'$term setSigType {sig}']
    for c in cells:
        lines += [f'set master [$db findMaster {c["model"]}]',f'if {{$master == "NULL"}} {{error "Missing {c["model"]}"}}',
                  f'set inst [odb::dbInst_create $block $master {c["name"]}]']
        for pin,net in bank.pins(c,orders).items():
            lines += [f'set term [$inst findITerm {pin}]',f'if {{$term == "NULL"}} {{error "Missing {c["name"]}.{pin}"}}',
                      f'set net [$block findNet {net}]',f'if {{$net == "NULL"}} {{set net [odb::dbNet_create $block {net}]}}','$term connect $net']
        if c['name'] in places:
            x,y=places[c['name']]['location'];lines += [f'$inst setLocation {round(x*1000)} {round(y*1000)}','$inst setPlacementStatus FIRM']
    lines += [f'set f [open {{{out/"connections.tsv"}}} w]',
              'foreach inst [$block getInsts] {foreach term [$inst getITerms] {',
              'set net [$term getNet]', 'if {$net == "NULL"} {error "Unconnected native terminal"}',
              'puts $f "[$inst getName]\t[[$term getMTerm] getName]\t[$net getName]"','}}','close $f',
              f'set f [open {{{out/"bterms.tsv"}}} w]',
              'foreach term [$block getBTerms] {puts $f "[$term getName]\t[$term getIoType]\t[$term getSigType]\t[[$term getNet] getName]"}','close $f',
              f'set f [open {{{out/"pins.tsv"}}} w]']
    for name in macros:
        lines += [f'set master [$db findMaster {name}]','foreach term [$master getMTerms] {set layers {}',
                  'foreach pin [$term getMPins] {foreach shape [$pin getGeometry] {lappend layers [[$shape getTechLayer] getName]}}',
                  f'puts $f "{name}\t[$term getName]\t[$term getIoType]\t[$term getSigType]\t[join [lsort -unique $layers] ,]"','}']
    lines += ['close $f',f'set f [open {{{out/"boxes.tsv"}}} w]']
    for name in places:
        lines += [f'set inst [$block findInst {name}]','set b [$inst getBBox]',f'puts $f "{name}\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"']
    lines += ['close $f',f'write_db {{{out/"macro_preflight.odb"}}}','exit']
    (out/'check.tcl').write_text('\n'.join(lines)+'\n')
    with (out/'openroad.log').open('w') as log:
        result=subprocess.run([tool,'-no_init','-exit',str(out/'check.tcl')],cwd=out,stdout=log,stderr=subprocess.STDOUT)
    errors=[];boxes={};observed={name:{} for name in macros}
    def rows(name):
        p=out/name
        return [line.split('\t') for line in p.read_text().splitlines()] if p.exists() else []
    expected={(c['name'],p,n) for c in cells for p,n in bank.pins(c,orders).items()}
    if Counter(map(tuple,rows('connections.tsv')))!=Counter(expected):errors.append('OpenDB instance connectivity changed')
    expected_terms={(p,'OUTPUT' if p=='OUT' else 'INOUT' if p in ['VPWR','VGND'] else 'INPUT',
                       'POWER' if p=='VPWR' else 'GROUND' if p=='VGND' else 'SIGNAL',p) for p in bank.PORTS}
    if Counter(map(tuple,rows('bterms.tsv')))!=Counter(expected_terms):errors.append('OpenDB public interface changed')
    for name,pin,direction,usage,layers in rows('pins.tsv'):observed[name][pin]=dict(direction=direction,use=usage,layers=layers.split(','))
    for name,macro in macros.items():
        wanted={p:dict(direction=v['direction'],use=v['use'],layers=[v['layer']]) for p,v in macro['pins'].items()}
        if observed[name]!=wanted:errors.append('OpenDB macro access mismatch: '+name)
    for name,*coords in rows('boxes.tsv'):boxes[name]=[int(v)/1000 for v in coords]
    if set(boxes)!=set(places):errors.append('Missing placed macro')
    try:no_overlaps(boxes,die)
    except ValueError as exc:errors.append(str(exc))
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()) or any(sha(Path(n))!=h for n,h in identity['pdk_files'].items()):raise ValueError('Assembly inputs changed')
    passed=result.returncode==0 and not errors
    report=dict(passed=passed,returncode=result.returncode,errors=errors,macro_types=len(macros),macro_instances=len(places),
                standard_cells=len(cells)-len(places),instances=len(cells),connected_iterms=len(expected),public_ports=len(bank.PORTS),boxes=boxes,
                native_network_equivalence_passed=True,route_complete=False,standard_cells_placed=False,io_pins_placed=False,qualified_phy=False,electrical_qualification_passed=False,
                scope='Exact full-bank native hierarchy, actual eleven-type LEF pin/78-macro placement and complete 94-instance OpenDB connectivity preflight only; no routing, DRC/LVS of the bank, native timing, ROM or PHY admission')
    (out/'macros.json').write_text(json.dumps({n:{k:v for k,v in value.items() if k!='pins'} for n,value in macros.items()},indent=2)+'\n')
    report['files']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['manifest.json','state.json','summary.json']}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'state.json').write_text(json.dumps(dict(status='assembly_complete',passed=passed,qualified_phy=False))+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics/weighted_bank_assembly_v2' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(Path(i['openroad']))!=i['openroad_sha256']):raise ValueError('Weighted-bank assembly context changed')
    candidate.bound(ROOT/i['parent']);shared.bound(ROOT/i['shared'])
    report=json.loads((out/'summary.json').read_text())
    if (any(sha(out/n)!=h for n,h in report['files'].items())
        or (out/'bank.spice').read_text()!=bank.spice(i['orders']) or (out/'bank.v').read_text()!=bank.verilog(i['orders'])):
        raise ValueError('Weighted-bank assembly outputs changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--shared',type=Path,required=True);a=p.parse_args()
    print(build(a.artifact.resolve(),a.shared.resolve()),flush=True)
