#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Use the frozen receiver replay with all compact-layout producers attested."""
import argparse
import json
from pathlib import Path
import probe_receiver_gain_candidate as replay


def prepare(parent,layout):
    physical=json.loads((layout/'summary.json').read_text())
    if 'layout_receiver_compact_candidate.py' not in physical['identity']['code']:
        raise ValueError('Expected the compact placement experiment')
    # The original replay producer is live and remains byte-for-byte frozen.
    # Its captured CODE parameter includes this adapter and every producer of
    # the selected physical artifact. Its existing run verifier checks them all.
    previous=replay.CODE
    try:
        replay.CODE=sorted(set(previous)|set(physical['identity']['code'])|{Path(__file__).name})
        return replay.prepare(parent,layout)
    finally:
        replay.CODE=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('parent',type=Path);a.add_argument('layout',type=Path)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.parent.resolve(),a.layout.resolve()),flush=True)
    else:replay.run(a.artifact.resolve())
