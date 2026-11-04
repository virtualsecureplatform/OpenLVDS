#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build and qualify one stronger native bit-4 transmission gate."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import weighted_fine_repair_v2 as unit
import build_weighted_fine_units_v3 as base
import diagnose_weighted_fine_charge_v2 as diagnosis

ROOT=base.ROOT
sha=base.sha
VERSION='native-largest-fine-double-tg-physical-v2.1'
CONTEXT='weighted_fine_repair_physical_v2'
layout=base.layout


def prepare(parent):
    dm=diagnosis.bound(parent);pilot=ROOT/dm['identity']['parent'];pm=json.loads((pilot/'manifest.json').read_text())
    receipt=ROOT/pm['identity']['fine_cells'];physical=ROOT/json.loads((receipt/'manifest.json').read_text())['identity']['parent']
    base.bound(physical);pr=json.loads((physical/'summary.json').read_text())
    if not pr['passed'] or len(pr['rows'])!=5 or not all(r['passed'] and r['drc_count']=='0' and r['lvs_passed'] for r in pr['rows']):
        raise ValueError('Require original five clean native fine cells')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';tech=pdk/'libs.tech/magic'
    pdks=[tech/'sky130A.magicrc',tech/'sky130A.tech',pdk/'libs.tech/netgen/sky130A_setup.tcl']+sorted(tech.rglob('*.tcl'))
    files=[parent/'manifest.json',parent/'summary.json',physical/'manifest.json',physical/'summary.json',physical/'state.json']
    files += [physical/unit.NAME/(unit.NAME+s) for s in ['.gds','.lef','.sch.spice','.lvs.log','.drc_count.txt']]
    code=[Path(__file__),Path(unit.__file__),Path(unit.previous.__file__),Path(unit.previous.fine.__file__),Path(base.__file__),Path(base.routing.__file__),Path(layout.__file__),
          Path(base.environment.__file__),Path(base.access.__file__),Path(base.access.geometry.__file__),Path(diagnosis.__file__),ROOT/'scripts/lvs_utils.py',ROOT/'build/apptainer/openlvds.sif.sha256']
    identity=dict(version=VERSION,diagnosis=str(parent.relative_to(ROOT)),original_physical=str(physical.relative_to(ROOT)),
        schematic_sha256=hashlib.sha256(unit.schematic().encode()).hexdigest(),inputs={str(p.relative_to(ROOT)):sha(p) for p in files+code},
        pdk_files={str(p):sha(p) for p in pdks},tools=base.environment.environment.tools())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    diagnosis.pilot.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or i['schematic_sha256']!=hashlib.sha256(unit.schematic().encode()).hexdigest()
        or base.environment.environment.tools()!=i['tools']):raise ValueError('Native fine repair context changed')
    diagnosis.bound(ROOT/i['diagnosis']);base.bound(ROOT/i['original_physical']);return m


def primitives(folder):
    ports,devices=layout.flatten(layout.circuits(unit.schematic()),unit.NAME)
    if ports!=unit.PORTS or len(devices)!=5:raise ValueError('Fine repair topology changed')
    keys=sorted({layout.primitive_key(d) for d in devices});commands=[];names={}
    for model,w,l in keys:
        name='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12];names[(model,w,l)]=name
        commands += [f'load {name} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',f'dict set p w {w}',f'dict set p l {l}']
        if 'fet_' in model:commands.append('dict set p botc 0')
        commands += [f'sky130::{model}_draw $p',f'save {name}']
    layout.invoke_magic(folder,'\n'.join(commands),'native_pcells')
    library={k:(n,layout.pcell_info(folder/(n+'.mag'))) for k,n in names.items()}
    record=[dict(model=k[0],width_um=k[1],length_um=k[2],cell=n,geometry=library[k][1],sha256=sha(folder/(n+'.mag'))) for k,n in names.items()]
    diagnosis.pilot.atomic(folder/'primitive_geometry.json',dict(devices=devices,library=record));return library,devices


def run(out):
    bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior fine repair geometry')
        diagnosis.pilot.atomic(out/'state.json',dict(status='routing',qualified_phy=False))
        folder=out/unit.NAME;folder.mkdir();library,devices=primitives(folder);configuration=base.plan(library,devices)
        result=base.routing.draw(folder,library,configuration,unit);result.update(layout.qualify(folder,unit.NAME))
        raw=folder/(unit.NAME+'.raw.lef');raw.write_bytes((folder/(unit.NAME+'.lef')).read_bytes())
        types=dict(NODE=('INPUT','SIGNAL'),EN=('INPUT','SIGNAL'),ENB=('INPUT','SIGNAL'),VDD=('INOUT','POWER'),VSS=('INOUT','GROUND'))
        text,pins=base.access.restrict(raw.read_text(),result['ports'],types);(folder/(unit.NAME+'.lef')).write_text(text)
        result.update(macro=unit.NAME,bit=4,integration_pins=pins,gds_sha256=sha(folder/(unit.NAME+'.gds')),lef_sha256=sha(folder/(unit.NAME+'.lef')),qualified_phy=False,electrical_qualification_passed=False)
        diagnosis.pilot.atomic(folder/'summary.json',result);bound(out)
        report=dict(rows=[result],passed=result['passed'],qualified_phy=False,electrical_qualification_passed=False,
            scope='Native bit-4 TG widths doubled, unchanged clear MOS and both MIMs; physical DRC/LVS only, no fresh RC, settling or full-bank admission')
        diagnosis.pilot.atomic(out/'summary.json',report);diagnosis.pilot.atomic(out/'state.json',dict(status='repair_physical_complete',passed=report['passed'],qualified_phy=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
