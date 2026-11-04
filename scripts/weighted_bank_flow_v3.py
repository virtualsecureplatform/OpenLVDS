# SPDX-License-Identifier: GPL-3.0-only
"""Keep physical instance identities while avoiding Verilog net/cell collisions."""
from copy import deepcopy
import weighted_bank_flow_v2 as base

SC=base.SC
POWER=base.POWER
parse=base.parse
blackboxes=base.blackboxes
control_placements=base.control_placements


def net_aliases(spec):
    instances={c['name'] for c in spec['cells']}
    nets={n for c in spec['cells'] for n in c['pins'].values()}
    public=set(spec['ports']);occupied=instances|nets|public;result={}
    for net in sorted((nets-public)&instances):
        stem='lvds_'+net+'_net';name=stem;index=0
        while name in occupied:index+=1;name=stem+'_'+str(index)
        result[net]=name;occupied.add(name)
    return result


def verilog(spec):
    adapted=deepcopy(spec);aliases=net_aliases(spec)
    for c in adapted['cells']:c['pins']={p:aliases.get(n,n) for p,n in c['pins'].items()}
    return base.verilog(adapted)


def connections_pass(rows,terms,spec):
    inverse={v:k for k,v in net_aliases(spec).items()}
    restored=[[name,model,pin,inverse.get(net,net)] for name,model,pin,net in rows]
    return base.connections_pass(restored,terms,spec)
