# SPDX-License-Identifier: GPL-3.0-only
"""Strengthen native storage paths and compare one/three real clock drivers.

No MOS or RC element is resized. Select the already qualified drive-4 NAND,
drive-8 inverter and actual extracted buffer macros. Whole-backend routing and
native all-PVT admission remain required, including physical parallel outputs.
"""
import native_clock_components_v2 as base

dcc=base.dcc
release=base.release
clean=base.clean
MODELS=base.MODELS
CLOCK_BUFFER=base.CLOCK_BUFFER
instance=base.instance
definitions=base.definitions
mapped_mos=base.mapped_mos


def strengthen(cells):
    return [(tag,{'nand2_2':'nand2_4','inv_1':'inv_8'}.get(short,short),pins) for tag,short,pins in cells]


def clean_source(rc,drivers):
    if drivers not in [1,3]:raise ValueError('Unqualified clock-driver experiment')
    rows=['.subckt '+clean.NAME+' '+' '.join(clean.PORTS)]
    for suffix in ['0','180']:
        for copy in range(drivers):
            rows.append(instance('clean'+suffix+'_'+str(copy),CLOCK_BUFFER,dict(A='F'+suffix,X='P'+suffix,VPWR='VPWR',VGND='VGND'),rc))
        rows.append(instance('monitor'+suffix,CLOCK_BUFFER,dict(A='P'+suffix,X='MON'+suffix,VPWR='VPWR',VGND='VGND'),rc))
    return '\n'.join(rows+['.ends '+clean.NAME,''])


def compose(rc):
    result={'cells.spice':'\n'.join(rc[n]['text'].rstrip() for n in sorted(rc))+'\n',
        'release.spice':base.logic(release.NAME,release.PORTS,strengthen(release.gates()),rc),
        'clean.spice':'* Candidate-specific extracted clock drivers are included in the selected DCC library.\n'}
    cells=[c for c in dcc.storage.gates(2) if not c[0].startswith('xor_')]
    cells += [('isolate_'+n,'buf_8',dict(A=n,X=n+'_iso')) for n in ['a','a_qb','b','b_qb']]
    text=base.logic(dcc.NAME,dcc.PORTS,strengthen(cells),rc);rows=text.splitlines()[:-1]
    rows.append(instance('xor','openlvds_tg_xor_p3_v2',dict(a_iso='a_iso',a_qb_iso='a_qb_iso',b_iso='b_iso',b_qb_iso='b_qb_iso',xor_out='xor_out',VDDD='VPWR',VSS='VGND'),rc))
    text='\n'.join(rows+['.ends '+dcc.NAME,''])
    for drivers in [1,3]:result[f'p3_c{drivers}.spice']=clean_source(rc,drivers)+text
    return result
