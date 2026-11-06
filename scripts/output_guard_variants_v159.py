# SPDX-License-Identifier: GPL-3.0-only
"""Output-compensation hypotheses; preserves baseline wiring, never admits GDS."""
from collections import Counter
import measured_bank_junction_reconstruction_v142 as cards
import native_clock_components_v2 as native
from native_bank_inventory_v51 import exact_number

CAP='sky130_fd_pr__cap_mim_m3_1'


def variant(text,top,labelled,keep):
    if type(keep) is not int or keep not in (0,1):raise ValueError('Choose zero or one shared output guard')
    defs=native.definitions(text)
    if set(defs)!={top}:raise ValueError('Require one flat baseline bank')
    ports,body=defs[top];targets=[];models=Counter()
    for w in body:
        if not w[0].upper().startswith('X'):continue
        end=next((k for k,t in enumerate(w) if '=' in t),len(w));model=w[end-1];models[model]+=1
        if model!=CAP or {labelled.get(n) for n in w[1:end-1]}!={'OUT','VGND'}:continue
        params=dict(t.split('=',1) for t in w[end:])
        if len(w[1:end-1])!=2 or set(params)!={'w','l'} or any(exact_number(v)!=2 for v in params.values()):
            raise ValueError('Output guard is not the measured native 2x2 MIM')
        targets.append(w[0])
    if len(targets)!=2:raise ValueError('Require exactly two actual output-to-ground native guards')
    targets.sort();removed=targets[keep:];records=cards.records(text);result=text
    for name in sorted(removed,key=lambda n:records[n][0],reverse=True):
        start,end=records[name];result=result[:start]+result[end:]
    after=native.definitions(result)
    expected=[w for w in body if w[0] not in removed]
    if after!={top:(ports,expected)} or cards.passive_lines(text)!=cards.passive_lines(result):
        raise ValueError('Output guard experiment changed another native/passive record')
    before_cards={n:text[a:b] for n,(a,b) in records.items() if n not in removed}
    after_cards={n:result[a:b] for n,(a,b) in cards.records(result).items()}
    if before_cards!=after_cards:raise ValueError('Retained native cards changed bytes')
    return result,dict(original_output_guards=targets,retained_output_guards=targets[:keep],removed_output_guards=removed,
                       original_native_mos=sum(n for m,n in models.items() if 'fet_' in m),original_native_mims=models[CAP],
                       candidate_native_mims=models[CAP]-len(removed),all_original_mos_and_other_native_cards_byte_identical=True,
                       all_original_explicit_passive_records_byte_identical=True,original_wire_rc_retained=True,
                       candidate_layout_qualified=False,qualified_phy=False)
