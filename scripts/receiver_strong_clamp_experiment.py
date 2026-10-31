#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare a four-times-stronger tracked reference and half clamp resistance."""
import argparse
from pathlib import Path
import re
import receiver_clamp_experiment as experiment
from receiver_clamp_experiment import source_variant as weak_source,TOP,MID
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TRACK='lvds_rx_track_strong'


def source_variant(source,clamped=True):
    source=weak_source(source,clamped)
    if not clamped:return source
    if TRACK in circuits(source):raise ValueError('Strong clamp reference already exists')
    block=text_block(source,TOP)
    old=f'XTRACK CO_TRACK CO_TRACK VDDD VSS {MID}'
    if block.count(old)!=1:raise ValueError('Unexpected tracked reference topology')
    block=block.replace(old,f'XTRACK CO_TRACK CO_TRACK VDDD VSS {TRACK}')
    extra=('XCLAMP2 CO CO_TRACK VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=1.25\n'
           'XCLAMP3 CO CO_TRACK VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=1.25\n')
    block=re.sub(r'(?im)^\.ends[^\n]*',lambda m:extra+m[0],block)
    source=replace(source,TOP,block)
    source+=f'''\n.subckt {TRACK} A Y VDD VSS
XP Y A VDD VDD sky130_fd_pr__pfet_01v8 w=32 l=0.15
XN Y A VSS VSS sky130_fd_pr__nfet_01v8 w=16 l=0.15
.ends {TRACK}
'''
    return source


def prepare(parent):
    previous_code=experiment.CODE;previous_source=experiment.source_variant
    try:
        # Reuse the frozen fixtures and waveform verifier, attesting this source
        # factory explicitly. Other processes and the preceding experiment stay
        # unchanged; every generated candidate/library is independently hashed.
        experiment.CODE=sorted(set(previous_code)|{Path(__file__).name})
        experiment.source_variant=source_variant
        return experiment.prepare(parent)
    finally:
        experiment.CODE=previous_code;experiment.source_variant=previous_source


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:experiment.run(a.artifact.resolve())
