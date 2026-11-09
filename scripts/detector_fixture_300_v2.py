# SPDX-License-Identifier: GPL-3.0-only
"""Canonicalize source voltage aliases and validate complete native translation."""
import re
import detector_inputs_300_v1 as inputs
from run_native_binary_v2 import translate


def fixture(out,s,devices):
    text=inputs.fixture(out,s,devices)
    matches=list(re.finditer(r'(?m)^\.print tran (.+)$',text))
    if len(matches)!=1:raise ValueError('Require one detector observation statement')
    match=matches[0];tokens=match[1].split();unique=[];seen=set()
    for token in tokens:
        if not re.fullmatch(r'V\([^()\s]+\)',token):raise ValueError('Unexpected detector observation token')
        key=token.replace(':','.').lower()
        if key not in seen:unique.append(token);seen.add(key)
    text=text[:match.start()]+'.print tran '+' '.join(unique)+text[match.end():]
    translate(text)
    return text
