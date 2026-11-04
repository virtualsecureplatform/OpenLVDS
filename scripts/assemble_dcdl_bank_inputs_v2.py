#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind all six physical macro types and check the complete bank in OpenDB.

This is a placement/interface experiment, not routed-bank or timing admission.
Every native paired driver needs its matching GDS, DRC/LVS and RC topology.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import build_compound_drivers_v3 as drivers
import extract_compound_drivers_v2 as driver_rc
import build_mim_base_4x4_v3 as base
import dcdl_mim_bank_physical_v2 as bank
from spice_library import checked_netlist

ROOT=drivers.ROOT
VERSION='six-macro-native-bank-assembly-preflight-v2.1'
sha=drivers.sha


def checked_abstract(parent):
    report=json.loads((parent/'summary.json').read_text());i=report['identity']
    if not report['passed'] or report['qualified_phy']:raise ValueError('Require passing unqualified unit abstract')
    if any(sha(ROOT/n)!=digest for n,digest in i['inputs'].items()):raise ValueError('Changed fine-unit abstract input')
    if (sha(ROOT/report['lef'])!=report['lef_sha256'] or sha(ROOT/report['gds'])!=report['gds_sha256']):
        raise ValueError('Changed fine-unit abstract output')
    return report


def inputs(compound,extraction,fine,shared):
    drivers.bound(compound);driver_rc.bound(extraction);base.bound(shared)
    report=json.loads((compound/'summary.json').read_text());rc=json.loads((extraction/'summary.json').read_text())
    if (not report['passed'] or not rc['passed'] or len(report['rows'])!=4 or len(rc['rows'])!=4
        or json.loads((extraction/'manifest.json').read_text())['identity']['parent']!=str(compound.relative_to(ROOT))):
        raise ValueError('Require matching passing four-driver physical/RC proofs')
    rc_rows={r['macro']:r for r in rc['rows']};macros={};witness=[]
    for row in report['rows']:
        name=row['macro'];folder=compound/name;proof=rc_rows[name];info=proof['extraction'];checked_netlist(info)
        if (row['drc_count']!='0' or not row['lvs_passed'] or not proof['rc_topology_passed']
            or info['gds_sha256']!=sha(folder/(name+'.gds'))
            or info['source_scope_sha256']!=sha(folder/(name+'.sch.spice'))
            or row['lef_sha256']!=sha(folder/(name+'.lef'))):raise ValueError('Compound provenance mismatch')
        macros[name]=dict(gds=[str(folder/(name+'.gds'))],lef=[str(folder/(name+'.lef'))],
            pins=row['integration_pins'],instances={})
        witness += [folder/(name+s) for s in ['.gds','.lef','.sch.spice','.drc_count.txt','.lvs.log']]
        witness += [ROOT/info['netlist'],extraction/name/'lvs.log',extraction/name/'summary.json']
    unit=checked_abstract(fine);name=bank.native.fine_unit.NAME
    macros[name]=dict(gds=[str(ROOT/unit['gds'])],lef=[str(ROOT/unit['lef'])],pins=unit['pins'],instances={})
    witness += [fine/'manifest.json',fine/'summary.json',ROOT/unit['gds'],ROOT/unit['lef']]
    result=json.loads((shared/'summary.json').read_text());name=base.NAME
    if not result['passed'] or result['drc_count']!='0' or not result['lvs_passed']:raise ValueError('Shared MIM physical proof failed')
    if sha(shared/(name+'.gds'))!=result['gds_sha256'] or sha(shared/(name+'.lef'))!=result['lef_sha256']:
        raise ValueError('Shared MIM output changed')
    macros[name]=dict(gds=[str(shared/(name+'.gds'))],lef=[str(shared/(name+'.lef'))],pins=result['integration_pins'],instances={})
    witness += [shared/(name+s) for s in ['.gds','.lef','.sch.spice','.drc_count.txt','.lvs.log']]
    for parent in [compound,extraction,shared]:witness += [parent/n for n in ['manifest.json','summary.json','state.json']]
    return macros,witness


def locations(cells):
    result={}
    for cell in cells:
        n=cell['name']
        if n.startswith('fine_unit'):
            i=int(n.removeprefix('fine_unit'));point=[5+15*(i%4),12+13*(i//4)]
        elif n=='shared_base':point=[140,10]
        elif n in ['input_buffer','output_buffer']:point=[68 if n=='input_buffer' else 86,4]
        elif cell['model'] in bank.COMPOUNDS.values():
            import re
            match=re.fullmatch(r'(forward|turn|pass|merge)(\d+)',n)
            if match is None:raise ValueError('Unknown core placement')
            point=[dict(forward=68,turn=86,**{'pass':104},merge=122)[match[1]],10+5*int(match[2])]
        else:continue
        result[n]=dict(location=point,orientation='N')
    return result


def no_overlaps(boxes,die):
    for name,box in boxes.items():
        if not (die[0]<=box[0]<box[2]<=die[2] and die[1]<=box[1]<box[3]<=die[3]):
            raise ValueError('Macro outside die: '+name)
    items=list(boxes.items())
    for i,(a,x) in enumerate(items):
        for b,y in items[i+1:]:
            if max(x[0],y[0])<min(x[2],y[2]) and max(x[1],y[1])<min(x[3],y[3]):
                raise ValueError('Macro overlap: '+a+' / '+b)


def build(compound,extraction,fine,shared):
    macros,files=inputs(compound,extraction,fine,shared);cells=bank.instances();places=locations(cells)
    for cell in cells:
        if cell['model'] in macros:macros[cell['model']]['instances'][cell['name']]=places[cell['name']]
    if sum(len(m['instances']) for m in macros.values())!=96:raise ValueError('Missing physical bank macro')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd'
    tech=pdk/'techlef/sky130_fd_sc_hd__nom.tlef';lef=pdk/'lef/sky130_fd_sc_hd.lef'
    tool=shutil.which('openroad')
    if tool is None:raise ValueError('Use scripts/env.sh --tools python3')
    files += [Path(__file__),Path(drivers.__file__),Path(driver_rc.__file__),Path(base.__file__),Path(bank.__file__),
              Path(bank.native.__file__),ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        pdk_files={str(p):sha(p) for p in [tech,lef]},openroad=tool,openroad_sha256=sha(Path(tool)),
        macros=macros,placements=places,die=[0,0,160,144],top=bank.name())
    out=ROOT/'build/diagnostics/dcdl_bank_assembly_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    # A real OpenDB reader checks sizes, origins and MTerm direction/use/layers.
    lines=[f'read_lef {{{tech}}}',f'read_lef {{{lef}}}']
    for m in macros.values():lines += [f'read_lef {{{m["lef"][0]}}}']
    lines += ['set db [ord::get_db]','set chip [odb::dbChip_create $db]',
              f'set block [odb::dbBlock_create $chip {bank.name()}]',
              f'set f [open {{{out/"pins.tsv"}}} w]']
    for name in macros:
        lines += [f'set master [$db findMaster {name}]','if {$master == "NULL"} {error "Missing bank macro"}',
            'foreach term [$master getMTerms] {', '  set layers {}',
            '  foreach pin [$term getMPins] {foreach shape [$pin getGeometry] {lappend layers [[$shape getTechLayer] getName]}}',
            f'  puts $f "{name}\t[$term getName]\t[$term getIoType]\t[$term getSigType]\t[join $layers ,]"','}']
    lines += ['close $f',f'set f [open {{{out/"boxes.tsv"}}} w]']
    for cell in cells:
        n=cell['name'];model=cell['model'];pins=dict(cell['pins'])
        if model not in macros:pins.update(VPWR='VPWR',VPB='VPWR',VGND='VGND',VNB='VGND')
        lines += [f'set master [$db findMaster {model}]',f'if {{$master == "NULL"}} {{error "Missing master {model}"}}',
                  f'set inst [odb::dbInst_create $block $master {n}]']
        for pin,net in pins.items():
            lines += [f'set term [$inst findITerm {pin}]',f'if {{$term == "NULL"}} {{error "Missing {n}.{pin}"}}',
                      f'set net [$block findNet {net}]',f'if {{$net == "NULL"}} {{set net [odb::dbNet_create $block {net}]}}',
                      '$term connect $net']
        if n in places:
            x,y=places[n]['location'];lines += [f'$inst setLocation {x*1000} {y*1000}','$inst setPlacementStatus FIRM',
                'set b [$inst getBBox]',f'puts $f "{n}\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"']
    lines += ['close $f',f'write_db {{{out/"macro_preflight.odb"}}}','exit']
    (out/'check.tcl').write_text('\n'.join(lines)+'\n')
    with (out/'openroad.log').open('w') as stream:
        process=subprocess.run([tool,'-no_init','-exit',str(out/'check.tcl')],cwd=out,stdout=stream,stderr=subprocess.STDOUT)
    observed={name:{} for name in macros};boxes={}
    if (out/'pins.tsv').exists():
        for line in (out/'pins.tsv').read_text().splitlines():
            macro,pin,direction,usage,layers=line.split('\t')
            observed[macro][pin]=dict(direction=direction,use=usage,layers=layers.split(','))
    if (out/'boxes.tsv').exists():
        for line in (out/'boxes.tsv').read_text().splitlines():
            n,*coords=line.split('\t');boxes[n]=[int(c)/1000 for c in coords]
    pin_ok=all(set(observed[n])==set(m['pins']) and all(observed[n][p]==dict(direction=v['direction'],use=v['use'],layers=['met3'])
        for p,v in m['pins'].items()) for n,m in macros.items())
    placement_error=None
    try:no_overlaps(boxes,identity['die'])
    except ValueError as exception:placement_error=str(exception)
    passed=process.returncode==0 and pin_ok and set(boxes)==set(places) and placement_error is None
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Bank inputs changed during preflight')
    # Configuration fragment is concrete and reviewable; PNR power routing and
    # whole-bank native characterization remain separate, unqualified work.
    (out/'macros.json').write_text(json.dumps({n:{k:v for k,v in m.items() if k!='pins'} for n,m in macros.items()},indent=2)+'\n')
    summary=dict(passed=passed,returncode=process.returncode,pins_passed=pin_ok,macro_count=len(places),
        logical_instances=len(cells),standard_cells=len(cells)-len(places),boxes=boxes,placement_error=placement_error,
        qualified_phy=False,electrical_qualification_passed=False,route_complete=False,
        scope='Six macro types and 174-instance OpenDB connectivity/placement preflight only; no routed bank or timing admission')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['compound','extraction','fine','shared']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(build(*(getattr(a,n).resolve() for n in ['compound','extraction','fine','shared'])),flush=True)
