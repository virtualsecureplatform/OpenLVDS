#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build an isolated receiver input-tail-current experiment; no release change."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from spice_library import replace
from layout import ROOT,circuits,flatten,primitive_key,pcell_info,invoke_magic,draw_macro,qualify


def source_variant(source,scale):
    if scale not in [1,2]:raise ValueError('Use the baseline or doubled input tails')
    ports,rows=circuits(source)['openlvds_receiver_core']
    tails={r[0]:r for r in rows if r[0] in ['XNT','XPT']}
    if set(tails)!={'XNT','XPT'}:raise ValueError('Missing complementary input tails')
    original=re.search(r'(?ims)^\.subckt openlvds_receiver_core\s.*?^\.ends[^\n]*',source)[0];changed=original
    for name,(label,nodes,model,params) in tails.items():
        expected=['NT','NB','VSS','VSS'] if name=='XNT' else ['PT','PB','VDDIO','VDDIO']
        kind='nfet' if name=='XNT' else 'pfet'
        if nodes!=expected or model!='sky130_fd_pr__'+kind+'_g5v0d10v5' or params!={'w':'12','l':'1'}:
            raise ValueError('Unknown input-tail topology')
        old=next(line for line in changed.splitlines() if line.startswith(label+' '))
        new=old.replace('w=12 ',f'w={12*scale} ')
        changed=changed.replace(old,new,1)
    return replace(source,'openlvds_receiver_core',changed)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scale',type=int,choices=[1,2],default=2);a=p.parse_args()
    source=source_variant((ROOT/'analog/openlvds.spice').read_text(),a.scale).encode()
    code={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in
          [Path(__file__).name,'layout.py','lvs_utils.py','spice_library.py']}
    identity=dict(source_sha256=hashlib.sha256(source).hexdigest(),code=code,input_tail_scale=a.scale)
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ROOT/'build/diagnostics/receiver_layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    (out/'candidate.spice').write_bytes(source);top='openlvds_receiver_core'
    ports,devices=flatten(circuits(source.decode()),top);keys=sorted({primitive_key(d) for d in devices});names={};body=[]
    for model,w,l in keys:
        cell='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12];names[(model,w,l)]=cell
        body += [f'load {cell} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',
                 f'dict set p w {w}',f'dict set p l {l}']
        if 'nfet' in model or 'pfet' in model:body+=['dict set p botc 0']
        body += [f'sky130::{model}_draw $p',f'save {cell}']
    invoke_magic(out,'\n'.join(body),'pcells')
    cells={key:(name,pcell_info(out/(name+'.mag'))) for key,name in names.items()}
    info=draw_macro(out,top,ports,devices,cells);info.update(qualify(out,top))
    summary=dict(identity=identity,source_sha256=identity['source_sha256'],fingerprint=fingerprint,
        diagnostic=True,qualified_phy=False,passed=info['passed'],designs={top:info})
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),passed=info['passed'],drc_count=info['drc_count'],lvs_passed=info['lvs_passed'])),flush=True)
    return 0 if info['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
