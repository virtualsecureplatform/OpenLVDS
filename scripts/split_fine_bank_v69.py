# SPDX-License-Identifier: GPL-3.0-only
"""Move the last twelve qualified fine units to the inverted selected node."""
import re
import regenerated_bank_v56 as source

NAME='openlvds_dcdl_c16_f32_split_fine_v69'
MOVED=tuple(range(19,31))
FINE='openlvds_mim_switch_2x3_v2'


def transform(text,old_top=source.NAME,moved=MOVED):
    if tuple(moved) not in ((),MOVED):raise ValueError('Use the declared baseline or twelve-unit split')
    definitions=source.native.definitions(text)
    if old_top not in definitions or FINE not in definitions:raise ValueError('Missing regenerated top or native fine cell')
    order=definitions[FINE][0]
    if order!=['NODE','EN','ENB','VDD','VSS']:raise ValueError('Qualified fine interface changed')
    active=False;seen=set();rows=[];changed=[]
    for line in text.splitlines():
        words=line.split()
        if words and words[0].lower()=='.subckt' and words[1]==old_top:
            if active:raise ValueError('Duplicate regenerated top')
            active=True;line=' '.join(['.subckt',NAME,*words[2:]])
        elif active and words and words[0].lower()=='.ends':
            active=False;line='.ends '+NAME
        elif active and words and re.fullmatch(r'Xfine_unit\d+',words[0]):
            index=int(words[0][10:])
            if index in seen or words[-1]!=FINE or words[1]!='OUT' or len(words)!=7:
                raise ValueError('Fine unit or original output loading changed')
            seen.add(index)
            if index in moved:words[1]='selected';line=' '.join(words);changed.append(index)
        rows.append(line)
    if active or seen!=set(range(31)) or set(changed)!=set(moved):raise ValueError('Incomplete original or split fine bank')
    result='\n'.join(rows)+'\n'
    if source.primitive_counts(text,old_top)!=source.primitive_counts(result,NAME):
        raise ValueError('Split architecture changed native device inventory')
    return result
