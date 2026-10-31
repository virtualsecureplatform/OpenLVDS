#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test wider complementary input pairs with the existing stronger clamp."""
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
    definitions=circuits(source);rows={r[0]:r for r in definitions[TOP][1]};block=text_block(source,TOP)
    for name,nodes,kind in [('XNP',['NL','INP','NT','VSS'],'nfet'),('XNN',['NR','INN','NT','VSS'],'nfet'),
                            ('XPP',['PL','INP','PT','VDDIO'],'pfet'),('XPN',['PR','INN','PT','VDDIO'],'pfet')]:
        row=rows[name]
        if row[1]!=nodes or row[2]!='sky130_fd_pr__'+kind+'_g5v0d10v5' or row[3]!=dict(w='20',l='0.5'):
            raise ValueError('Unexpected input-pair geometry or terminals')
        pattern=r'(?m)^'+name+r'[^\n]*$';old=re.search(pattern,block)[0]
        block,count=re.subn(pattern,lambda _:old.replace('w=20','w=40'),block)
        if count!=1:raise ValueError('Ambiguous input transistor')
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
