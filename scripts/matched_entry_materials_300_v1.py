#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched linear 100 ps entry materials; preparation only, no source admission."""
import json
from pathlib import Path
import bank_entry_waveform_300_v2 as waveform
import probe_tg2_entry_domain_300_v1 as entry

ROOT=entry.ROOT
SETTINGS=((100,.5,True),(100,.6,True),(100,.5,False),(100,.6,False))


def specifications(base):
    required=dict(process='ss',temperature=40,frequency_mhz=310,coarse=0,fine=0,cycles=8,stop_ns=40,load_ff=20)
    if any(base[k]!=v for k,v in required.items()):raise ValueError('Require original SS40/310 loaded zero specification')
    return [dict(base,input_slew_ps=slew,duty=duty) for slew,duty,_ in SETTINGS]


def fixture(out,source_identity,library,spec,centered):
    # Construct the exact original loaded circuit, changing only its known
    # independent ideal source. No new transistor/model is introduced.
    temporary=dict(spec,input_slew_ps=250)
    text,obs=entry.fixture(out,source_identity,library,temporary,centered)
    original=entry.waveform.source(temporary)
    if text.count(original)!=1:raise ValueError('Exact original PWL source changed')
    return text.replace(original,waveform.source(spec),1),obs


def tasks(out,source_manifest,library):
    base=source_manifest['tasks'][0]['spec']
    for k,(spec,(_,_,centered)) in enumerate(zip(specifications(base),SETTINGS)):
        text,obs=fixture(out,source_manifest['identity'],library,spec,centered)
        yield dict(id=str(k),spec=spec,centered=centered),text,obs
