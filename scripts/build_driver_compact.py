#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build an isolated complete driver from verified source, banks and gate tiles."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

import driver_compact_geometry as geometry
import driver_finger_banks as banks
import probe_driver_finger_pcells as source
from layout import circuits, flatten, qualify, invoke_magic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = source.sha


def build(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/driver_inverter_tiles'):
        raise ValueError('Require checked driver inverter tiles')
    r = json.loads((parent/'summary.json').read_text())
    if (parent.name != hashlib.sha256(json.dumps(r['identity'], sort_keys=True).encode()).hexdigest()[:16] or
            r.get('passed') is not True or len(r['tiles'])!=5 or r['inverter_instances']!=9 or
            not all(x['passed'] and x['drc_count']=='0' and x['lvs_passed'] for x in r['tiles']) or
            any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require all five unchanged DRC/LVS-qualified tiles')
    inputs = dict(r['identity']['inputs'])
    inputs[str((parent/'summary.json').relative_to(ROOT))] = sha(parent/'summary.json')
    inputs.update({str((parent/n).relative_to(ROOT)):h for n,h in r['files'].items()})
    ready = [ROOT/n for n in inputs if Path(n).is_relative_to('build/diagnostics/driver_shape_source_verification') and Path(n).name=='summary.json']
    if len(ready)!=1: raise ValueError('Require exact complete source readiness')
    campaign,_,_ = source.source_ready(ready[0])
    text = (campaign/'tt_25_negative_op/source.spice').read_text()
    top = source.recipe.taper.TOP
    ports, original = flatten(circuits(text),top)
    grouped = banks.group(original)
    bank_parent = ROOT/r['identity']['parent']
    bank_report = json.loads((bank_parent/'summary.json').read_text())
    if not bank_report['passed']: raise ValueError('Bank admission failed')
    library = {tuple(x['recipe'][n] for n in ['model','w','l','nf']):x for x in bank_report['banks']}
    tiles = {tuple(tuple(part) for part in x['recipe']):x for x in r['tiles']}
    code = dict(r['identity']['code'])
    code.update({n:sha(ROOT/'scripts'/n) for n in ['build_driver_compact.py','driver_compact_geometry.py',
                                                  'build_driver_inverter_tiles.py','driver_inverter_geometry.py']})
    identity = dict(parent=str(parent.relative_to(ROOT)),inputs=inputs,code=code,
        technology=r['identity']['technology'],source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        scope='Complete compact driver physical trial. Same admitted source and all original '
              'independent fingers. DRC/LVS precede GDS extraction, RC audit and native '
              'electrical qualification. No automatic PHY admission.')
    out = ROOT/'build/diagnostics/driver_compact_layout'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)

    def unchanged():
        if (any(sha(ROOT/n)!=h for n,h in inputs.items()) or
                any(sha(ROOT/'scripts'/n)!=h for n,h in code.items()) or
                any(sha(Path(n))!=h for n,h in identity['technology'].items())):
            raise ValueError('Compact driver context changed')

    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        unchanged()
        if (out/'summary.json').exists():
            old=json.loads((out/'summary.json').read_text())
            if old['identity']!=identity or any(sha(out/n)!=h for n,h in old['files'].items()):
                raise ValueError('Compact driver evidence changed')
            return out
        if (out/'manifest.json').exists(): raise ValueError('Prior partial compact driver retained')
        capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False))
        (out/'candidate.spice').write_text(text)
        for path in parent.glob('*.mag'): shutil.copyfile(path,out/path.name)
        body=[]
        cells={}
        for d in grouped:
            if banks.mos(d): continue
            k=d['model'],d['params']['w'],d['params']['l']
            cell='pass_'+hashlib.sha256(json.dumps(k).encode()).hexdigest()[:12]
            if cell in cells: continue
            cells[cell]=d
            body += [f'load {cell} -silent','box values 0 0 0 0',f'set p [sky130::{d["model"]}_defaults]',
                     f'dict set p w {k[1]}',f'dict set p l {k[2]}',f'sky130::{d["model"]}_draw $p',f'save {cell}']
        invoke_magic(out,'\n'.join(body),'passive_pcells')
        wrappers={}
        for i,d in enumerate(x for x in grouped if not banks.mos(x)):
            k=d['model'],d['params']['w'],d['params']['l']
            cell='pass_'+hashlib.sha256(json.dumps(k).encode()).hexdigest()[:12]
            wrappers[d['name']]=geometry.passive(out,'passive_'+str(i),cell,d)
        info=geometry.write(out,top,ports,original,grouped,library,tiles,wrappers)
        info.update(qualify(out,top))
        print(top,info['drc_count'],info['lvs_passed'],flush=True)
        unchanged()
        files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['.execution.lock','summary.json']}
        capture_manifest(out/'summary.json',dict(identity=identity,source_sha256=identity['source_sha256'],
            designs={top:info},passed=info['passed'],files=files,qualified_phy=False,physical_admission=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent',type=Path)
    args=parser.parse_args()
    print(build(args.parent.resolve()),flush=True)
