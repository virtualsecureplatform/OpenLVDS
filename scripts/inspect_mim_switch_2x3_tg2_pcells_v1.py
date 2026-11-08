#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect actual PDK device geometry before compact fine-bank unit placement.

Never write active layout/current selections. This artifact contains primitive
PCell geometry and the five-port source schematic, not a routed or electrically
qualified macro. Keep its evidence intact when building a routing revision.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import layout
import mim_switch_2x3_tg2_v1 as unit

ROOT=layout.ROOT
VERSION='mim-switch-2x3-double-tg-pdk-geometry-v1'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def tools():
    result={}
    for name in ['magic','netgen']:
        path=shutil.which(name)
        if path is None:raise ValueError('Use scripts/env.sh --tools python3')
        result[name]=dict(path=path,sha256=sha(Path(path)))
    return result


def prepare():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    paths=[Path(__file__),Path(unit.__file__),Path(layout.__file__),ROOT/'scripts/lvs_utils.py',
           ROOT/'requirements.json',ROOT/'clocking_300mhz.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    pdk_files=[pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):sha(p) for p in paths},
        pdk_files={str(p):sha(p) for p in pdk_files},tools=tools(),schematic_sha256=hashlib.sha256(unit.schematic().encode()).hexdigest())
    out=ROOT/'build/diagnostics/mim_switch_2x3_tg2_pcells_v1'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'unit.spice').write_text(unit.schematic());return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/mim_switch_2x3_tg2_pcells_v1') or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=v for n,v in i['code'].items())
        or any(sha(Path(n))!=v for n,v in i['pdk_files'].items()) or tools()!=i['tools']
        or sha(out/'unit.spice')!=i['schematic_sha256']):raise ValueError('PCell inspection inputs changed')
    return m


def run(out):
    bound(out)
    if (out/'summary.json').exists() or (out/'state.json').exists():raise ValueError('Retain prior PCell execution')
    (out/'state.json').write_text(json.dumps(dict(status='inspecting',qualified_phy=False))+'\n')
    ports,devices=layout.flatten(layout.circuits(unit.schematic()),unit.NAME)
    keys=sorted({layout.primitive_key(d) for d in devices});commands=[];names={}
    for model,w,l in keys:
        name='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12];names[(model,w,l)]=name
        commands += [f'load {name} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',
            f'dict set p w {w}',f'dict set p l {l}']
        if 'fet_' in model:commands.append('dict set p botc 0')
        commands += [f'sky130::{model}_draw $p',f'save {name}']
    layout.invoke_magic(out,'\n'.join(commands),'pcells')
    library=[dict(model=k[0],width_um=k[1],length_um=k[2],cell=n,
                  geometry=layout.pcell_info(out/(n+'.mag')),sha256=sha(out/(n+'.mag'))) for k,n in names.items()]
    bound(out)
    report=dict(ports=ports,devices=devices,library=library,qualified_phy=False,routed=False,
        scope='Actual PDK primitive geometry inspection only; no macro DRC/LVS, electrical or PHY admission')
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'state.json').write_text(json.dumps(dict(status='primitive_complete',qualified_phy=False))+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',nargs='?',type=Path);a=p.parse_args()
    if a.action in ('prepare','campaign'):out=prepare();print(out,flush=True)
    elif a.artifact is None:p.error('Provide the prepared artifact')
    else:out=a.artifact.resolve()
    if a.action in ('run','campaign'):print(json.dumps(run(out),indent=2),flush=True)
