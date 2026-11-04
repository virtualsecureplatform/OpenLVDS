# SPDX-License-Identifier: GPL-3.0-only
"""Real native buffer fanout for the permanent clock-conditioner experiment."""
from native_static_cells_v2 import inline
from dcc_nand_mid_shunt_v2 import CAP,devices

NAME='openlvds_clock_clean_pair_v2'
PORTS=['F0','F180','P0','P180','MON0','MON180','VPWR','VGND']


def source(library):
    cells=[]
    for suffix in ['0','180']:
        cells += [('clean'+suffix,'buf_8',dict(A='F'+suffix,X='P'+suffix)),
                  ('monitor'+suffix,'buf_8',dict(A='P'+suffix,X='MON'+suffix))]
    body=inline(cells,library);private=sorted({n for d in devices(body) for n in d['nodes'] if '__' in n})
    rows=['.subckt '+NAME+' '+' '.join(PORTS),body.rstrip()]
    rows += [f'XPRIVATE{i} {node} VGND {CAP} w=2 l=2' for i,node in enumerate(private)]
    rows += [f'XFIXED{i} {node} VGND {CAP} w=4 l=4' for i,node in enumerate(['P0','P180','MON0','MON180'])]
    return '\n'.join(rows+['.ends '+NAME,''])


def mapped_mos(text,mapping,prefix):
    """Read actual native MOS terminals, including the unchanged RC bias body."""
    result=[]
    for line in text.splitlines():
        words=line.split()
        if not words or not words[0].startswith('X'):continue
        first=next((i for i,w in enumerate(words) if '=' in w),len(words));model=words[first-1];nodes=words[1:first-1]
        if model==CAP:
            if len(nodes)!=2:raise ValueError('MIM port count changed')
            continue
        if not model.startswith('sky130_fd_pr__') or not ('nfet_' in model or 'pfet_' in model) or len(nodes)!=4:
            raise ValueError('Unknown native clock/bias active device')
        if '01v8' in model:limit=1.95
        elif model in ['sky130_fd_pr__pfet_g5v0d10v5','sky130_fd_pr__nfet_g5v0d10v5']:limit=5.5
        else:raise ValueError('Unknown native clock/bias voltage domain')
        result.append(dict(name=prefix+':'+words[0],model=model,limit_v=limit,
            terminals=[mapping.get(n,prefix+':'+n) for n in nodes]))
    return result
