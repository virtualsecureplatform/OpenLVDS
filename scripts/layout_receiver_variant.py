# SPDX-License-Identifier: GPL-3.0-only
"""Build a source-bound diagnostic receiver without touching active layouts."""
import hashlib
import json
from pathlib import Path
from layout import ROOT,circuits,flatten,primitive_key,pcell_info,invoke_magic,draw_macro,qualify


def build(source,metadata,producers):
    source=source.encode();names=set(producers)|{Path(__file__).name,'layout.py','lvs_utils.py','spice_library.py'}
    if set(metadata)&{'source_sha256','code'}:raise ValueError('Reserved receiver identity fields')
    identity=dict(metadata,source_sha256=hashlib.sha256(source).hexdigest(),
                  code={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in sorted(names)})
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ROOT/'build/diagnostics/receiver_layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    (out/'candidate.spice').write_bytes(source);top='openlvds_receiver_core'
    ports,devices=flatten(circuits(source.decode()),top);keys=sorted({primitive_key(d) for d in devices});cells={};body=[]
    for model,w,l in keys:
        cell='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12];cells[(model,w,l)]=cell
        body += [f'load {cell} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',
                 f'dict set p w {w}',f'dict set p l {l}']
        if 'nfet' in model or 'pfet' in model:body+=['dict set p botc 0']
        body += [f'sky130::{model}_draw $p',f'save {cell}']
    invoke_magic(out,'\n'.join(body),'pcells')
    library={key:(name,pcell_info(out/(name+'.mag'))) for key,name in cells.items()}
    info=draw_macro(out,top,ports,devices,library);info.update(qualify(out,top))
    summary=dict(identity=identity,source_sha256=identity['source_sha256'],fingerprint=fingerprint,
                 diagnostic=True,qualified_phy=False,passed=info['passed'],designs={top:info})
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return out,summary
