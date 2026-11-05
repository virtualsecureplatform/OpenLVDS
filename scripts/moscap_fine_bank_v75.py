# SPDX-License-Identifier: GPL-3.0-only
"""Small complementary gate-cap loads before the existing final inverter."""
import re
import regenerated_bank_v56 as source
from build_compound_drivers_v3 import cell_definition
from audit_rc_comments_v2 import collapse

WIDTHS=dict(w042='.42',w084='.84',w126='1.26')
OLD_FINE='openlvds_mim_switch_2x3_v2'


def name(profile):
    if profile not in WIDTHS:raise ValueError('Unknown gate-cap fine quantum')
    return 'openlvds_internal_moscap_'+profile+'_v75'


def unit(text,profile):
    top=name(profile);fine=top+'_unit'
    native=source.native.definitions(collapse(cell_definition(text,OLD_FINE)))[OLD_FINE]
    if native[0]!=['NODE','EN','ENB','VDD','VSS']:raise ValueError('Original fine public interface changed')
    mos=[];guards=[];cap=None
    for words in native[1]:
        end=next((i for i,t in enumerate(words) if '=' in t),len(words));model=words[end-1]
        if 'fet_' in model:mos.append(' '.join(words))
        elif model=='sky130_fd_pr__cap_mim_m3_1':
            params=dict(t.split('=',1) for t in words[end:])
            if set(words[1:3])=={'ENB','VSS'} and {k:float(v) for k,v in params.items()}=={'w':2.,'l':2.}:
                guards.append(' '.join(words));continue
            if cap is not None or 'VSS' not in words[1:3] or {k:float(v) for k,v in params.items()}!={'w':2.,'l':3.}:raise ValueError('Original fine MIM changed')
            cap=next(n for n in words[1:3] if n!='VSS')
        else:raise ValueError('Unexpected wire-collapsed fine primitive')
    if len(mos)!=3 or len(guards)!=1 or cap is None:raise ValueError('Incomplete original fine switch')
    rows=['.subckt '+fine+' NODE EN ENB VDD VSS',*mos,*guards,
        'Xgatecap_n VSS '+cap+' VSS VSS sky130_fd_pr__nfet_01v8 w='+WIDTHS[profile]+' l=.15',
        'Xgatecap_p VDD '+cap+' VDD VDD sky130_fd_pr__pfet_01v8 w='+WIDTHS[profile]+' l=.15','.ends '+fine]
    return '\n'.join(rows)+'\n'


def transform(text,profile):
    top=name(profile);fine=top+'_unit';defs=source.native.definitions(text)
    if source.NAME not in defs:raise ValueError('Require original regenerated component bank')
    unit_text=unit(text,profile)
    ports,body=defs[source.NAME];bank=['.subckt '+top+' '+' '.join(ports)];seen=set()
    for words in body:
        w=list(words)
        if re.fullmatch(r'Xfine_unit\d+',w[0]):
            k=int(w[0][10:])
            if k in seen or w[1]!='OUT' or w[-1]!=OLD_FINE:raise ValueError('Original fine bank loading changed')
            seen.add(k);w[1]='selected';w[-1]=fine
        bank.append(' '.join(w))
    if seen!=set(range(31)):raise ValueError('Incomplete original fine bank')
    bank.append('.ends '+top)
    # The original qualified component definitions stay byte-preserved.
    original=cell_definition(text,source.NAME)
    if text.count(original)!=1:raise ValueError('Ambiguous original regenerated top')
    result=text.replace(original,'',1)+'\n'+unit_text+'\n'.join(bank)+'\n'
    counts=source.primitive_counts(result,top)
    if sum(v for k,v in counts.items() if 'fet_' in k)!=1013 or counts.get('sky130_fd_pr__cap_mim_m3_1')!=37:
        raise ValueError('Internal gate-cap native inventory changed')
    return result
