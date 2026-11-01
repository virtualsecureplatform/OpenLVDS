#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Strengthen only the decision PMOS mirror/load at the original decision-tail current."""
import argparse
from pathlib import Path
import re

import receiver_clamp_experiment as experiment
from receiver_unclamped_restore_experiment import source_variant as standard_source
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP='openlvds_receiver_core'
CODE=['receiver_decision_load_experiment.py','receiver_unclamped_restore_experiment.py',
      'receiver_fast_restore_experiment.py','receiver_vref_clamp_experiment.py',
      'receiver_light_clamp_experiment.py','receiver_light_decision_experiment.py',
      'receiver_strong_clamp_experiment.py','receiver_clamp_experiment.py',
      'layout_receiver_gain_candidate.py','layout.py','dll_campaign.py','spice_library.py']


def strengthen_loads(source):
    rows={row[0]:row for row in circuits(source)[TOP][1]}
    expected={
        'XCT':('XCT',['CT','NBC','VSS','VSS'],'sky130_fd_pr__nfet_01v8',dict(w='64',l='0.5')),
        'XC0':('XC0',['CL','PN','CT','VSS'],'sky130_fd_pr__nfet_01v8',dict(w='8',l='0.15')),
        'XC1':('XC1',['CO','PP','CT','VSS'],'sky130_fd_pr__nfet_01v8',dict(w='8',l='0.15')),
        'XCD':('XCD',['CL','CL','VDDD','VDDD'],'sky130_fd_pr__pfet_01v8',dict(w='8',l='0.15')),
        'XCM':('XCM',['CO','CL','VDDD','VDDD'],'sky130_fd_pr__pfet_01v8',dict(w='8',l='0.15')),
    }
    if any(rows.get(name)!=row for name,row in expected.items()) or any(n.startswith('XCLAMP') for n in rows):
        raise ValueError('Expected the original unclamped 64 um tail and 8 um decision devices')
    block=text_block(source,TOP)
    block,count=re.subn(r'(?m)^(XC[DM][^\n]*\bw=)8(\s+l=0\.15\s*)$',r'\g<1>32\2',block)
    if count!=2:raise ValueError('Expected exactly the two original PMOS decision loads')
    return replace(source,TOP,block)


def source_variant(source,clamped=True):
    # Legacy experiment task labels select the modified/control factory;
    # neither variant contains the removed CO clamp resistors.
    base=standard_source(source,True)
    return strengthen_loads(base) if clamped else base


def prepare(parent):
    code,factory=experiment.CODE,experiment.source_variant
    try:
        experiment.CODE=sorted(set(code)|set(CODE))
        experiment.source_variant=source_variant
        return experiment.prepare(parent)
    finally:experiment.CODE,experiment.source_variant=code,factory


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run']);parser.add_argument('artifact',type=Path);args=parser.parse_args()
    if args.action=='prepare':print(prepare(args.artifact.resolve()),flush=True)
    else:experiment.run(args.artifact.resolve())
