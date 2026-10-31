#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test original decision sizes with doubled input tails and the stronger clamp."""
import argparse
from pathlib import Path
import re
import receiver_clamp_experiment as experiment
from receiver_strong_clamp_experiment import source_variant as previous_source
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP='openlvds_receiver_core'


def source_variant(source,clamped=True):
    source=previous_source(source,clamped)
    if not clamped:return source
    rows={r[0]:r for r in circuits(source)[TOP][1]};block=text_block(source,TOP)
    expected={
        'XCT':(['CT','NBC','VSS','VSS'],'nfet',128,'0.5'),
        'XC0':(['CL','PN','CT','VSS'],'nfet',16,'0.15'),
        'XC1':(['CO','PP','CT','VSS'],'nfet',16,'0.15'),
        'XCD':(['CL','CL','VDDD','VDDD'],'pfet',16,'0.15'),
        'XCM':(['CO','CL','VDDD','VDDD'],'pfet',16,'0.15')}
    for name,(nodes,kind,width,length) in expected.items():
        row=rows[name]
        if row[1]!=nodes or row[2]!='sky130_fd_pr__'+kind+'_01v8' or row[3]!=dict(w=str(width),l=length):
            raise ValueError('Unexpected doubled decision device '+name)
        pattern=r'(?m)^'+name+r'[^\n]*$';old=re.search(pattern,block)[0]
        new=re.sub(r'\bw=\S+',f'w={width//2}',old)
        block,count=re.subn(pattern,lambda _:new,block)
        if count!=1:raise ValueError('Ambiguous decision transistor')
    return replace(source,TOP,block)


def prepare(parent):
    previous_code=experiment.CODE;previous_factory=experiment.source_variant
    try:
        experiment.CODE=sorted(set(previous_code)|{'receiver_strong_clamp_experiment.py',Path(__file__).name})
        experiment.source_variant=source_variant
        return experiment.prepare(parent)
    finally:
        experiment.CODE=previous_code;experiment.source_variant=previous_factory


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:experiment.run(a.artifact.resolve())
