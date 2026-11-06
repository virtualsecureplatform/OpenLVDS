#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retain the failed v191 block and repair only captured directory-qualified names."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import build_repaired_clock_counter_v191 as source
import native_gds_names_v192 as names
from probe_digital_dcc_v2 import atomic,sha
from lvs_utils import clean_match

ROOT=source.ROOT
NAME=source.NAME
VERSION='counter-gds-directory-prefix-only-canonical-repair-v192.1'
CONTEXT='repaired_clock_counter_names_v192'
SCOPE='Name-only repair of retained zero-DRC unique-LVS 21-macro counter; every GDS mask/text/placement retained and native masters rechecked; no shared-wire RC/timing/all-PVT/PHY admission'


def cad(action,spec,out):
    path=out/(action+'_spec.json');path.write_text(json.dumps(spec,indent=2)+'\n')
    result=subprocess.run([source.repaired.CAD,str(ROOT/'scripts/native_gds_names_v192.py'),action,str(path)],cwd=ROOT,capture_output=True,text=True)
    (out/(action+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode:raise ValueError('Name-only GDS '+action+' refused:\n'+result.stderr[-2500:])
    return json.loads(result.stdout)


def prepare(parent):
    m=source.bound(parent);i=m['identity'];folder=parent/NAME;state=json.loads((parent/'state.json').read_text())
    if state.get('status')!='physical_exception' or 'Missing native output master clock_mim_2x2_v2' not in state.get('error',''):raise ValueError('Require exact retained v191 native-master naming failure')
    if (folder/(NAME+'.drc_count.txt')).read_text().strip()!='0' or not clean_match((folder/(NAME+'.lvs.log')).read_text()):raise ValueError('Original geometry or connectivity failed')
    paths=[parent/'manifest.json',parent/'state.json',parent/'execution_error.json',*[p for p in folder.iterdir() if p.is_file()]]
    paths += [ROOT/n for n in {*i['inputs'],*i['code']}]+[Path(__file__),Path(names.__file__)]
    prefix='/work/OpenLVDS/'+str(folder.relative_to(ROOT))+'/'
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),prefix=prefix,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  pdk_files=i['pdk_files'],tools=i['tools'],cad=i['cad'],scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or source.native.environment.tools()!=i['tools'] or sha(Path(source.repaired.CAD))!=i['cad']['sha256']):raise ValueError('Name-only counter repair context changed')
    return m


def run(out):
    m=bound(out);i=m['identity'];parent=ROOT/i['parent'];pi=json.loads((parent/'manifest.json').read_text())['identity'];original=parent/NAME
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial naming repair')
        atomic(out/'state.json',dict(status='canonicalizing',qualified_phy=False));folder=out/NAME;folder.mkdir()
        try:
            mapping=cad('inspect',dict(components=[str(ROOT/macro['folder']/(model+'.gds')) for model,macro in pi['macros'].items()],
                gds=str(original/(NAME+'.gds')),prefix=i['prefix'],top=NAME),out)
            changes={}
            for old,new in mapping.items():
                path=original/(new+'.mag')
                if not path.exists():raise ValueError('Missing retained native MAG '+new)
                text,n=names.mag_names(path.read_text(),mapping);(folder/(new+'.mag')).write_text(text);changes[new]=n
            (folder/(NAME+'.sch.spice')).write_bytes((original/(NAME+'.sch.spice')).read_bytes())
            physical=source.layout.qualify(folder,NAME)
            if not physical['passed']:raise ValueError('Canonical counter DRC/LVS failed; retain new artifact')
            raw=folder/(NAME+'.raw.lef');raw.write_bytes((folder/(NAME+'.lef')).read_bytes())
            public={pin:dict(layer='metal5',x_um=.3,y_um=pi['buses'][pin],width_um=2. if pin in ('VGND','VPWR') else pi['configuration']['bus_width_um']) for pin in source.PORTS}
            types={pin:('OUTPUT' if pin in ('CLK','PREPARE','RESET_N') else 'INPUT','SIGNAL') for pin in source.PORTS if pin not in ('VPWR','VGND')};types.update(VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
            lef,pins=source.access.restrict(raw.read_text(),public,types)
            if source.access.geometry.geometry(lef)!=source.access.geometry.geometry((original/(NAME+'.lef')).read_text()):raise ValueError('Canonical counter abstract geometry changed')
            (folder/(NAME+'.lef')).write_text(lef)
            unchanged=cad('verify',dict(before=str(original/(NAME+'.gds')),after=str(folder/(NAME+'.gds')),mapping=mapping),out)
            native=source.native_master_witness(pi['macros'],folder/(NAME+'.gds'),pi['cells'],pi['placements'])
            bound(out)
            result=dict(physical=physical,name_bijection=mapping,mag_use_name_changes=changes,unchanged_geometry=unchanged,native_master_witness=native,
                ports=public,integration_pins=pins,gds_sha256=sha(folder/(NAME+'.gds')),lef_sha256=sha(folder/(NAME+'.lef')),
                files={str(p.relative_to(out)):sha(p) for p in out.glob('**/*') if p.is_file() and p.name not in ('manifest.json','state.json') and not p.name.startswith('.')},
                physical_name_repair_passed=True,shared_wire_rc_qualified=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            atomic(out/'summary.json',result);atomic(out/'state.json',dict(status='complete',passed=True,qualified_phy=False));return out
        except Exception as e:atomic(out/'state.json',dict(status='failed',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
