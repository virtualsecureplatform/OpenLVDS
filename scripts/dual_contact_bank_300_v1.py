# SPDX-License-Identifier: GPL-3.0-only
"""Replace coarse TG contact routing, retaining full native observation coverage."""
from copy import deepcopy
import json
from pathlib import Path
import fast_entry_damping_bank_300_v1 as baseline
import build_dual_contact_tg_300_v3 as physical
import qualify_dual_contact_tg_rc_300_v1 as qualification

source=baseline.source
native=baseline.native
VERSION='dual-contact-coarse-bank-300-v1'
KINDS=('combined',)
OLD='openlvds_tg_quad_stacked_nlvt_v27'
PROOF=source.ROOT/'build/diagnostics/dual_contact_tg_rc_proof_300_v1/51037b99d9110009'


def component():
    qualification.bound(PROOF)
    r=json.loads((PROOF/'summary.json').read_text())
    if not r['component_rc_qualified'] or r['qualified_phy'] or r['bank_timing_qualified']:
        raise ValueError('Require complete component-only RC proof')
    if any(qualification.sha(PROOF/n)!=h for n,h in r['files'].items()):
        raise ValueError('Dual-contact current proof outputs changed')
    info=r['rows'][0]['extraction']
    return physical.checked_netlist(info).replace(physical.NAME,OLD)


def transform(library,top,observations,kind):
    if kind not in KINDS:raise ValueError('Unknown dual-contact intervention')
    revised,bank,old_obs,revision=baseline.transform(library,top,observations,kind)
    original=source.SOURCE.definition(revised,OLD)
    replacement=component()
    result=revised.replace(original,replacement,1)
    ports=native.definitions(result)[bank][0]
    pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports}
    devices=native.mapped_mos(result,bank,pins,'XD')
    # Native extraction can reorder X0/X1 and RC-separated terminal names.
    # Match each primitive by hierarchy plus model; never retain stale gate maps.
    def key(d):
        coarse=any(x in d['name'] for x in (':Xswitch',':Xleaf_parallel',':Xroot_parallel'))
        return (d['name'].rsplit(':',1)[0] if coarse else d['name'],d['model'])
    after={key(d):d for d in devices};before={d['name']:d for d in old_obs['devices']}
    if len(after)!=len(devices) or {key(d) for d in old_obs['devices']}!=set(after):
        raise ValueError('Native transistor hierarchy/model inventory changed')
    for d in old_obs['devices']:
        if after[key(d)]!=d and not any(x in d['name'] for x in (':Xswitch',':Xleaf_parallel',':Xroot_parallel')):
            raise ValueError('Unrelated transistor observation changed')
    gates=deepcopy(old_obs['programming_gates'])
    for g in gates:
        d=after[key(before[g['device']])]
        g.update(device=d['name'],gate_node=d['terminals'][1])
    if len({g['device'] for g in gates})!=len(gates):raise ValueError('Duplicate programming gate')
    return result,bank,dict(devices=devices,controls=deepcopy(old_obs['controls']),programming_gates=gates),dict(
        revision,version=VERSION,dual_contact_coarse_tg=True,component_proof=str(PROOF.relative_to(source.ROOT)),
        qualified_phy=False)
