#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retain all public phase/control observations in four-section native decks."""
import re
import four_bank_fixture_300_v1 as previous
from run_native_binary_v2 import translate


def fixture(original,library,top,identity,*,codes=((0,0),(0,0),(0,0))):
    text,obs=previous.fixture(original,library,top,identity,codes=codes)
    # Public boundary nodes can connect only to extracted R/C ports, so a
    # complete MOS-terminal map alone does not guarantee these observations.
    public={'IN','OUT','B1_OUT','B2_OUT','B3_OUT','VDD'}
    public.update(('' if k==0 else f'B{k}_')+f'{kind}{j}'
                  for k in range(4) for kind,count in (('S',4),('E',31)) for j in range(count))
    match=re.search(r'(?m)^\.print tran (.*)$',text)
    if match is None:raise ValueError('Missing original native observation statement')
    tokens=match[1].split()+['V('+n+')' for n in sorted(public)]
    unique=[];seen=set()
    for token in tokens:
        key=token.lower().replace(':','.')
        if key not in seen:unique.append(token);seen.add(key)
    text=text[:match.start()]+'.print tran '+' '.join(unique)+text[match.end():]
    translate(text)
    return text,obs
