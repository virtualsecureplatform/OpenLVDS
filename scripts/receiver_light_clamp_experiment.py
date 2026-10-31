#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reduce clamp conductance for the original-size receiver decision stage."""
import argparse
from pathlib import Path
import re
import receiver_clamp_experiment as experiment
from receiver_light_decision_experiment import source_variant as previous_source
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP='openlvds_receiver_core'


def source_variant(source,clamped=True):
    source=previous_source(source,clamped)
    if not clamped:return source
    block=text_block(source,TOP);rows={r[0]:r for r in circuits(source)[TOP][1]}
    for name in ['XCLAMP2','XCLAMP3']:
        row=rows[name]
        if row[1:]!=(['CO','CO_TRACK','VSS'],'sky130_fd_pr__res_high_po_0p35',dict(w='0.35',l='1.25')):
            raise ValueError('Unexpected clamp resistor '+name)
        block,count=re.subn(r'(?m)^'+name+r'[^\n]*\n','',block)
        if count!=1:raise ValueError('Ambiguous clamp resistor')
    return replace(source,TOP,block)


def prepare(parent):
    previous_code=experiment.CODE;previous_factory=experiment.source_variant
    try:
        experiment.CODE=sorted(set(previous_code)|{'receiver_light_decision_experiment.py','receiver_strong_clamp_experiment.py',Path(__file__).name})
        experiment.source_variant=source_variant
        return experiment.prepare(parent)
    finally:
        experiment.CODE=previous_code;experiment.source_variant=previous_factory


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:experiment.run(a.artifact.resolve())
