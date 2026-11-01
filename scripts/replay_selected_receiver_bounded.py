#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Use certified physical-pin PWL sources; reconstruct unused TX observations afterward."""
import argparse
from contextlib import contextmanager
import json,re
from pathlib import Path
import numpy as np
import replay_selected_receiver as replay
from bounded_pin_replay import PINS,simplify
from receiver_static_diagnosis import capture_manifest
BASE_FIXTURE=replay.fixture
BASE_READ=replay.read_wave
NAME=Path(__file__).name


def sources(wave,headers):
    t=wave[:,1];values=np.column_stack([wave[:,headers['V('+n+')']] for n in PINS]);indices,certificate=simplify(t,values)
    rows=['VREC_'+n+' '+n+' 0 PWL('+ ' '.join(f'{t[i]:.17g} {values[i,j]:.17g}' for i in indices)+')' for j,n in enumerate(PINS)]
    # These names remain available to the original probe validator. They
    # have no electrical connection to the RX; actual recorded observations
    # are restored in analysis instead of forcing simulator breakpoints.
    rows += ['VREC_'+n+' '+n+' 0 0' for n in replay.RECORDED if n not in PINS]
    return '\n'.join(rows)+'\n',certificate


def fixture(parent,out,stop):
    text=BASE_FIXTURE(parent,out,stop)
    return re.sub(r'(?m)^\.print tran .*$', '.print tran '+' '.join('V('+n+')' for n in replay.NAMES[:9]),text)


@contextmanager
def profile(parent):
    reference,headers=BASE_READ(parent/'bench.cir.prn')
    previous=(replay.recorded_sources,replay.fixture,replay.read_wave,replay.CODE)
    def expanded(path):
        wave,head=BASE_READ(path)
        if all('V('+n+')' in head for n in replay.NAMES):return wave,head
        if any(head.get('V('+n+')')!=i+2 for i,n in enumerate(replay.NAMES[:9])):raise ValueError('Unexpected physical replay vectors')
        columns=[wave[:,i] for i in range(11)]
        for n in replay.NAMES[9:]:
            columns.append(np.interp(wave[:,1],reference[:,1],reference[:,headers['V('+n+')']]))
        return np.column_stack(columns),dict(INDEX=0,TIME=1,**{'V('+n+')':i+2 for i,n in enumerate(replay.NAMES)})
    try:
        replay.recorded_sources=lambda w,h:sources(w,h)[0]
        replay.fixture=fixture;replay.read_wave=expanded
        replay.CODE=set(replay.CODE)|{NAME,'bounded_pin_replay.py'}
        yield reference,headers
    finally:replay.recorded_sources,replay.fixture,replay.read_wave,replay.CODE=previous


def certify(root,reference,headers):
    text,certificate=sources(reference,headers)
    if (root/'pins.spice').read_text()!=text:raise ValueError('Bounded pin sources changed')
    certificate.update(pins_sha256=replay.digest(root/'pins.spice'),parent_waveform_sha256=replay.digest(replay.ROOT/json.loads((root/'manifest.json').read_text())['identity']['parent']/'bench.cir.prn'),
        observations_restored_from_parent=replay.NAMES[9:],producer_sha256=replay.digest(Path(__file__)),numerical_helper_sha256=replay.digest(replay.ROOT/'scripts/bounded_pin_replay.py'))
    capture_manifest(root/'pin_replay_certificate.json',certificate)
    return certificate


def prepare(parent,sanity,control=None):
    with profile(parent) as (reference,headers):
        root=replay.prepare(parent,sanity,control);certify(root,reference,headers)
    return root


def run(root,wait_slot=None):
    identity=json.loads((root/'manifest.json').read_text())['identity']
    if identity['code'].get(NAME)!=replay.digest(Path(__file__)):raise ValueError('Bounded replay producer changed')
    parent=replay.ROOT/identity['parent']
    with profile(parent) as (reference,headers):
        certify(root,reference,headers);report=replay.run(root,wait_slot);certify(root,reference,headers)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--sanity',type=Path);p.add_argument('--control',type=Path);p.add_argument('--wait-slot',type=int,choices=range(6));a=p.parse_args()
    if a.action=='prepare':
        if a.sanity is None:p.error('--sanity is required')
        print(prepare(a.artifact.resolve(),a.sanity.resolve(),a.control.resolve() if a.control else None),flush=True)
    else:run(a.artifact.resolve(),a.wait_slot);print(a.artifact.resolve()/'summary.json',flush=True)
