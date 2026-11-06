# SPDX-License-Identifier: GPL-3.0-only
"""Increase only low0's output MIM guards for measured cold-corner margin, retaining native MOS and old wire RC."""
from decimal import Decimal
import re
import native_clock_components_v2 as native
from build_compound_drivers_v3 import cell_definition
import measured_bank_junction_reconstruction_v142 as cards
from native_bank_inventory_v51 import exact_number

MODEL='openlvds_nand2b_4_o1_stack_guard_pair_v2'
CAP='sky130_fd_pr__cap_mim_m3_1'


def libraries(cells,module,dimension):
    if dimension not in ('2','3'):raise ValueError('Use the declared guard dimensions')
    text=cell_definition(cells,MODEL);ports,body=native.definitions(text)[MODEL]
    parent={}
    def root(n):
        parent.setdefault(n,n)
        if parent[n]!=n:parent[n]=root(parent[n])
        return parent[n]
    for w in body:
        if w[0].upper().startswith('R'):
            parent[root(w[1])]=root(w[2])
    targets=[]
    for w in body:
        if CAP not in w:continue
        k=w.index(CAP)
        if {root(n) for n in w[1:k]}!={root('Y'),root('VGND')}:continue
        params=dict(v.split('=',1) for v in w[k+1:])
        if len(w[1:k])!=2 or set(params)!={'l','w'} or any(exact_number(v)!=1 for v in params.values()):
            raise ValueError('Require the two native 1x1 output guards')
        targets.append(w[0])
    if len(targets)!=2:raise ValueError('Require exactly two output guards, excluding private stack guards')
    records=cards.records(text);candidate=text
    for name in sorted(targets,key=lambda n:records[n][0],reverse=True):
        start,end=records[name];card=text[start:end]
        changed=re.sub(r'\b([wl])=\S+',lambda m:m[1]+'='+dimension,card)
        candidate=candidate[:start]+changed+candidate[end:]
    new=MODEL+'_out'+dimension.replace('.','p')+'_v168'
    candidate=re.sub(r'\b'+MODEL+r'\b',new,candidate)
    rows=re.findall(r'(?m)^Xlow0_set_pair [^\n]+$',module)
    if len(rows)!=1 or rows[0].split()[-1]!=MODEL:raise ValueError('Require one original low0 setter')
    altered=module.replace(rows[0],rows[0][:-len(MODEL)]+new,1)
    after=native.definitions(candidate)[new][1]
    old_other=[w for w in body if w[0] not in targets];new_other=[w for w in after if w[0] not in targets]
    if old_other!=new_other or cards.passive_lines(text)!=cards.passive_lines(candidate):raise ValueError('Non-output native or passive records changed')
    return cells+'\n'+candidate,altered,dict(output_guards=sorted(targets),dimension_um=dimension,
        area_scale=str(Decimal(dimension)**2),all_original_library_bytes_retained=True,
        other_native_and_passive_cards_preserved=True,only_low0_setter_retargeted=True,
        candidate_layout_qualified=False,qualified_phy=False)
