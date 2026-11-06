# SPDX-License-Identifier: GPL-3.0-only
"""Resolve the physically present, unlabeled even-array drain end contact."""
from copy import deepcopy
import re
import native_bank_inventory_v51 as inventory


def complete_accesses(row,mag,spice):
    n=row['spec']['fingers'];ports,devices=inventory.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',spice),row['top']+'_flat')
    unknown={d['nodes'][j] for d in devices for j in (0,2) if d['nodes'][j] not in ports}
    accesses=deepcopy(row['terminal_accesses']);drains=[t for t in accesses if re.fullmatch('D[0-9]+',t['name'])];sources=[t for t in accesses if re.fullmatch('S[0-9]+',t['name'])];bulks=[t for t in accesses if t['name']=='B']
    if n%2 or len(devices)!=n or len(unknown)!=1 or len(drains)!=n//2 or len(sources)!=n//2 or len(bulks)!=1:raise ValueError('Unexpected native even-array terminal coverage')
    first=[t for t in drains if t['name']=='D0']
    if len(first)!=1:raise ValueError('Require unique native left drain access')
    first=first[0];center=bulks[0]['x_um'];bbox=row['geometry']['bbox']
    if abs((bbox[0]+bbox[2])/2-center)>1e-9 or first['x_um']>=center:raise ValueError('Native array symmetry changed')
    terminal=dict(first,name='D_end',x_um=2*center-first['x_um'])
    if any(abs(t['x_um']-terminal['x_um'])<1e-9 for t in drains+sources):raise ValueError('Drain end is already declared or ambiguous')
    layers={};layer=None
    for line in mag.splitlines():
        if line.startswith('<< '):layer=line.split()[1];layers.setdefault(layer,[])
        elif line.startswith('rect '):layers[layer].append([int(v)*.005 for v in line.split()[1:]])
    for key in (first['layer'],'viali'):
        if not any(r[0]-1e-9<=terminal['x_um']<=r[2]+1e-9 and r[1]-1e-9<=terminal['y_um']<=r[3]+1e-9 for r in layers.get(key,[])):raise ValueError('Mirrored end is not an actual native contacted diffusion')
    accesses.append(terminal)
    return accesses,dict(unlabelled_native_drain_nodes=sorted(unknown),added_physical_end_access=terminal,native_contact_and_viali_verified=True,ideal_net_alias_added=False)
