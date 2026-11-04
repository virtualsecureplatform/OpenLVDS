#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build isolated fine-switch GDS/LEF and independently check DRC/LVS.

No source electrical certificate or active layout/current selection is created.
The exact primitive geometry inspection is retained as a parent artifact.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import inspect_mim_switch_pcells_v2 as pcells
import mim_switch_unit_layout_v3 as routing

ROOT=pcells.ROOT
unit=pcells.unit
layout=pcells.layout
VERSION='mim-switch-unit-physical-prototype-v2.2'
sha=pcells.sha


def prepare(parent,configuration=None):
    pm=pcells.bound(parent);report=json.loads((parent/'summary.json').read_text())
    if report['routed'] or report['qualified_phy']:raise ValueError('Require original primitive inspection')
    for d in report['library']:
        if sha(parent/(d['cell']+'.mag'))!=d['sha256']:raise ValueError('Primitive geometry changed')
    files=[Path(__file__),Path(routing.__file__),Path(unit.__file__),Path(pcells.__file__),Path(layout.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):sha(p) for p in files},
        parent=str(parent.relative_to(ROOT)),
        parent_files={str((parent/n).relative_to(ROOT)):sha(parent/n) for n in ['manifest.json','summary.json','unit.spice']},
        pdk_files=pm['identity']['pdk_files'],tools=pcells.tools(),configuration=configuration or routing.plan())
    out=ROOT/'build/diagnostics/mim_switch_unit_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for d in report['library']:shutil.copy2(parent/(d['cell']+'.mag'),out/(d['cell']+'.mag'))
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/mim_switch_unit_physical_v2') or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=v for n,v in {**i['code'],**i['parent_files']}.items())
        or any(sha(Path(n))!=v for n,v in i['pdk_files'].items()) or pcells.tools()!=i['tools']):
        raise ValueError('Fine-unit physical inputs changed')
    report=json.loads((ROOT/i['parent']/'summary.json').read_text())
    for d in report['library']:
        if sha(out/(d['cell']+'.mag'))!=d['sha256']:raise ValueError('Copied primitive geometry changed')
    return m,report


def run(out):
    m,parent=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior unit execution')
        (out/'state.json').write_text(json.dumps(dict(status='routing',qualified_phy=False))+'\n')
        library={(d['model'],d['width_um'],d['length_um']):(d['cell'],d['geometry']) for d in parent['library']}
        result=routing.draw(out,library,m['identity']['configuration'])
        result.update(layout.qualify(out,unit.NAME));bound(out)
        result.update(unit_physical_passed=result['passed'],qualified_phy=False,
            scope='Isolated native five-device unit DRC/LVS only; no array, RC timing, PVT or PHY admission')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='unit_physical_complete',passed=result['passed'],qualified_phy=False))+'\n')
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--plan',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out,json.loads(a.plan.read_text()) if a.plan else None);print(out,flush=True)
    if a.action in ('run','campaign'):print(json.dumps(run(out),indent=2),flush=True)
