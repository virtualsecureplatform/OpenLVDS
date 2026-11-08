#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded-memory all-sample native MOS terminal envelopes; no exclusions."""
import numpy as np

VERSION='all-sample-block-native-terminal-envelopes-300-v1'


def envelopes(names,wave,devices,*,block_rows=256):
    if type(block_rows) is not int or block_rows<1:
        raise ValueError('Require a positive integral row block')
    canonical=[n.lower().replace(':','.') for n in names]
    if (wave.ndim!=2 or wave.shape[0]<2 or wave.shape[1]!=len(names)
            or wave.dtype.kind!='f' or wave.dtype.itemsize!=8
            or len(set(canonical))!=len(canonical) or not devices
            or len({d['name'] for d in devices})!=len(devices)):
        raise ValueError('Require unambiguous complete float64 native terminal maps')
    columns={n:k for k,n in enumerate(canonical)};indices=[]
    for d in devices:
        if len(d['terminals'])!=4 or not np.isfinite(d['limit_v']) or d['limit_v']<=0:
            raise ValueError('Require four actual MOS terminals and a positive finite limit')
        row=[]
        for node in d['terminals']:
            column='v('+node.lower().replace(':','.')+')'
            if node!='0' and column not in columns:raise ValueError('Missing actual native terminal: '+node)
            row.append(-1 if node=='0' else columns[column])
        indices.append(row)
    indices=np.asarray(indices,dtype=np.intp);ground=indices<0;safe=np.maximum(indices,0)
    peaks=np.zeros(len(devices),dtype=np.float64)
    for start in range(0,len(wave),block_rows):
        # take() owns its output, so ground substitution cannot mutate raw data.
        values=np.take(wave[start:start+block_rows],safe,axis=1)
        np.copyto(values,0.,where=ground[None,:,:])
        if not np.isfinite(values).all():raise ValueError('Nonfinite actual native terminal sample')
        span=np.max(values,axis=2)-np.min(values,axis=2)
        peaks=np.maximum(peaks,np.max(span,axis=0))
    return [dict(device=d['name'],maximum_terminal_difference_v=float(peak),limit_v=d['limit_v'],
                 passed=bool(peak<=d['limit_v'])) for d,peak in zip(devices,peaks)]
