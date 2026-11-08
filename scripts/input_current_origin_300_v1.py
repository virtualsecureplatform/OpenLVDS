#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare a DC-zero input-source current-origin diagnostic; never admission.

The external load changes the ideal BIN source's branch current, not its
voltage expression. Full native voltage/DC/event parity remains mandatory.
"""
import re
from run_native_binary_v2 import translate

VERSION='dc-zero-immediate-input-current-origin-diagnostic-300-v1'
CARD='I_BENCH_INPUT_CENTER IN 0 DC 0 PWL(0 0 2p 1m 40n 1m)'


def fixture(original,library):
    lines=re.findall(r'(?m)^BIN IN 0 V=.+$',original)
    if (len(lines)!=1 or original.count('.tran 2p 40n 0 2p')!=1
            or 'I_BENCH_INPUT_CENTER' in original
            or re.search(r'(?i)\bi\s*\(\s*bin\s*\)',original+'\n'+library)
            or re.search(r'(?im)^[FH]\S*\s',original+'\n'+library)):
        raise ValueError('Require original ideal BIN without source-current feedback and complete 40ns fixture')
    text=original.replace(lines[0]+'\n',lines[0]+'\n'+CARD+'\n',1)
    if text.count(CARD)!=1 or text.replace(CARD+'\n','',1)!=original:
        raise ValueError('Input-origin trial changed more than the declared external load')
    translate(text)
    return text
