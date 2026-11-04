# SPDX-License-Identifier: GPL-3.0-only
"""Tune only the eight native TG widths around the passing buffered topology."""
import dcc_tg_buffered_v2 as baseline

NAME='openlvds_dcc_tg_ratio_v2'
PORTS=baseline.PORTS
storage=baseline.storage
direct=baseline
devices=baseline.devices
VARIANTS={
    'p3':dict(ff_drive=2,n_width_um=1,p_width_um=3,isolation_buffer='buf_8'),
    'p4':dict(ff_drive=2,n_width_um=1,p_width_um=4,isolation_buffer='buf_8'),
    'n05p2':dict(ff_drive=2,n_width_um=.5,p_width_um=2,isolation_buffer='buf_8')}


def source(variant,library):
    if variant not in VARIANTS:raise ValueError('Undeclared TG width ratio')
    text,metadata=baseline.source('tg1',library);rows=[];changed=0;spec=VARIANTS[variant]
    for line in text.splitlines():
        if line.startswith('Xtg_'):
            words=line.split();model=words[5]
            if model not in [baseline.N,baseline.P] or len(words)!=8 or words[-1]!='l=0.15':
                raise ValueError('Baseline native TG transistor changed')
            width=spec['n_width_um'] if model==baseline.N else spec['p_width_um'];words[6]=f'w={width:g}'
            line=' '.join(words);changed+=1
        rows.append(line)
    if changed!=8:raise ValueError('Require exactly eight physical TG devices')
    rows[0]='.subckt '+NAME+' '+' '.join(PORTS)
    if rows[-1]!='.ends '+baseline.NAME:raise ValueError('Baseline TG boundary changed')
    rows[-1]='.ends '+NAME
    return '\n'.join(rows)+'\n',dict(metadata,hardware=spec)
