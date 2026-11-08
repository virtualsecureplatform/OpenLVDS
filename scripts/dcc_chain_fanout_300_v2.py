#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Actual DCC fanout with explicit public phase observations."""
import re
import dcc_chain_fanout_300_v1 as previous
from run_native_binary_v2 import translate

namespace=previous.namespace
mapped_mos=previous.mapped_mos
PORTS=previous.PORTS


def fixture(chain_deck,bank_library,dcc_library,dcc_include):
    text,obs=previous.fixture(chain_deck,bank_library,dcc_library,dcc_include)
    match=re.search(r'(?m)^\.print tran (.*)$',text)
    if match is None:raise ValueError('Missing actual combined observations')
    tokens=match[1].split()+[f'V({n})' for n in ('IN','OUT','B1_OUT','B2_OUT','B3_OUT','VDD','DCC_RESET_N','DCC0_OUT','DCC1_OUT')]
    unique=[];seen=set()
    for token in tokens:
        key=token.lower().replace(':','.')
        if key not in seen:unique.append(token);seen.add(key)
    text=text[:match.start()]+'.print tran '+' '.join(unique)+text[match.end():]
    translate(text)
    return text,obs
