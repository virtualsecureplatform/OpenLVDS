#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build isolated matched driver geometries for a native diagnostic comparison."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from driver_restore_variant import source_variant,TOP
from layout import circuits,flatten,primitive_key,pcell_info,invoke_magic,draw_macro,qualify

ROOT=Path(__file__).resolve().parents[1]
VARIANTS={'source_control':False,'restore_64_24':True}
PORTS='D OUTP OUTN VREF PB NB VDDIO VDDD VSS'.split()
CODE=['layout_driver_restore_candidate.py','driver_restore_variant.py','driver_restore_candidate_rc.py',
      'layout.py','lvs_utils.py','spice_library.py','dll_campaign.py','extract.py','audit_rc.py','reduce_rc.py']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_source(variant):
    if variant not in VARIANTS:raise ValueError('Unknown matched driver variant')
    source=source_variant((ROOT/'analog/openlvds.spice').read_text(),VARIANTS[variant])
    if circuits(source)[TOP][0]!=PORTS:raise ValueError('Driver public port order changed')
    return source


def build(variant):
    source=selected_source(variant)
    identity=dict(variant=variant,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        restoration_widths_um=[64,24] if VARIANTS[variant] else [48,40],
        code={name:digest(ROOT/'scripts'/name) for name in sorted(CODE)},
        scope='Diagnostic driver geometry only; no source functional, electrical or PHY qualification')
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ROOT/'build/diagnostics/driver_layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    with (out/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cached=out/'summary.json'
        if cached.exists():
            summary=json.loads(cached.read_text())
            if summary['identity']!=identity or (out/'candidate.spice').read_text()!=source or any(
                    digest(out/name)!=stamp for name,stamp in summary['files'].items()):
                raise ValueError('Captured driver geometry or physical evidence changed')
            return out,summary
        (out/'candidate.spice').write_text(source)
        ports,devices=flatten(circuits(source),TOP)
        keys=sorted({primitive_key(device) for device in devices});cells={};body=[]
        for model,w,l in keys:
            cell='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12]
            cells[(model,w,l)]=cell
            body += [f'load {cell} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',
                     f'dict set p w {w}',f'dict set p l {l}']
            if 'nfet' in model or 'pfet' in model:body+=['dict set p botc 0']
            body += [f'sky130::{model}_draw $p',f'save {cell}']
        invoke_magic(out,'\n'.join(body),'pcells')
        library={key:(name,pcell_info(out/(name+'.mag'))) for key,name in cells.items()}
        info=draw_macro(out,TOP,ports,devices,library);info.update(qualify(out,TOP))
        files=[out/(TOP+suffix) for suffix in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']]
        summary=dict(identity=identity,source_sha256=identity['source_sha256'],fingerprint=fingerprint,
            diagnostic=True,qualified_phy=False,passed=info['passed'],designs={TOP:info},
            files={path.name:digest(path) for path in files})
        cached.write_text(json.dumps(summary,indent=2)+'\n')
    return out,summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variant',choices=VARIANTS)
    args=parser.parse_args();out,summary=build(args.variant)
    print(json.dumps(dict(output=str(out),passed=summary['passed'])),flush=True)
    raise SystemExit(0 if summary['passed'] else 1)
