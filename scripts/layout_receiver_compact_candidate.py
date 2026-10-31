#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reorder unchanged receiver device banks to shorten high-impedance wires."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

from layout import ROOT,circuits,flatten,primitive_key,pcell_info,invoke_magic,draw_macro,qualify
from layout_receiver_gain_candidate import source_variant

TOP='openlvds_receiver_core'
WEIGHTS={'PP':5.,'PN':5.,'CO':4.,'CL':2.,'CT':1.,
         'NL':.5,'NR':.5,'PL':.5,'PR':.5,'NT':.25,'PT':.25,
         'RESTORE0':.5,'RESTORE1':.5}


def banks(devices):
    grouped={}
    for device in devices:
        key=re.sub(r'_F\d+$','',device['name'])
        grouped.setdefault(key,[]).append(device)
    if len({d['name'] for d in devices})!=len(devices):raise ValueError('Duplicate receiver device')
    return list(grouped.values())


def spans(groups,library):
    points=defaultdict(list);cursor=10.
    for group in groups:
        for device in group:
            bb=library[primitive_key(device)][1]['bbox'];cx=cursor-bb[0]+2.5
            cursor=cx+bb[2]+2.5
            for net in set(device['nodes']):points[net].append(cx)
    return {net:max(xs)-min(xs) for net,xs in points.items()}


def objective(groups,library):
    lengths=spans(groups,library)
    values={name:lengths.get(TOP+'__'+name,0.) for name in WEIGHTS}
    return sum(WEIGHTS[n]*v for n,v in values.items())+2.*abs(values['PP']-values['PN'])


def ordered(devices,library):
    """Deterministic bank swaps; retain every PCell/finger and its terminals."""
    groups=banks(devices);before=objective(groups,library);score=before;steps=0
    while True:
        selected=None;best=score
        for i in range(len(groups)):
            for j in range(i+1,len(groups)):
                trial=groups.copy();trial[i],trial[j]=trial[j],trial[i]
                value=objective(trial,library)
                if value<best-1e-6:best=value;selected=trial
        if selected is None:break
        groups=selected;score=best;steps+=1
    result=[d for group in groups for d in group]
    if sorted(json.dumps(d,sort_keys=True) for d in result)!=sorted(json.dumps(d,sort_keys=True) for d in devices):
        raise ValueError('Placement changed receiver devices or connectivity')
    return result,dict(objective_before_um=before,objective_after_um=score,swap_steps=steps,
        original_spans_um=spans(banks(devices),library),ordered_spans_um=spans(groups,library),
        device_order=[d['name'] for d in result])


def main():
    source=source_variant((ROOT/'analog/openlvds.spice').read_text())
    producers=[Path(__file__).name,'layout_receiver_gain_candidate.py','layout_receiver_tail_candidate.py',
               'layout.py','lvs_utils.py','spice_library.py']
    identity=dict(input_tail_scale=2,decision_scale=2,
        restoration='Three inverters: P/N widths 4/2, 8/4, 16/8; unchanged overall polarity',
        placement='Deterministic weighted wire-span bank swaps; original schematic unchanged',
        weights=WEIGHTS,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        code={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in producers})
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ROOT/'build/diagnostics/receiver_layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    (out/'candidate.spice').write_text(source)
    ports,devices=flatten(circuits(source),TOP);cells={};body=[]
    for model,w,l in sorted({primitive_key(d) for d in devices}):
        cell='p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12];cells[(model,w,l)]=cell
        body += [f'load {cell} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',
                 f'dict set p w {w}',f'dict set p l {l}']
        if 'nfet' in model or 'pfet' in model:body+=['dict set p botc 0']
        body += [f'sky130::{model}_draw $p',f'save {cell}']
    invoke_magic(out,'\n'.join(body),'pcells')
    library={key:(name,pcell_info(out/(name+'.mag'))) for key,name in cells.items()}
    devices,placement=ordered(devices,library)
    (out/'placement.json').write_text(json.dumps(placement,indent=2)+'\n')
    info=draw_macro(out,TOP,ports,devices,library);info.update(qualify(out,TOP))
    summary=dict(identity=identity,source_sha256=identity['source_sha256'],fingerprint=fingerprint,
                 diagnostic=True,qualified_phy=False,passed=info['passed'],designs={TOP:info})
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),passed=summary['passed'],placement=placement)),flush=True)
    return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
