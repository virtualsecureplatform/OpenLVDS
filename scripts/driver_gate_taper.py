# SPDX-License-Identifier: GPL-3.0-only
"""Two bounded real-MOS restoration tapers; no bridge, mirror or CMFB changes."""
from dll_campaign import text_block
from spice_library import replace

TOP='openlvds_driver_core'
SHIFT='lvds_shift18_33_restore_64_24'
UNIT='lvds_inv33_gate_unit_16_8'
VARIANTS={'taper_16_32_64':(1,2,4),'taper_16_64_128':(1,4,8)}


def transform(source,variant):
    if variant not in VARIANTS:raise ValueError('Select a declared gate-restoration taper')
    if '.subckt '+UNIT+' ' in source:raise ValueError('Gate taper already installed')
    driver=text_block(source,TOP);old='XLS D DP DN NB VDDIO VDDD VSS '+SHIFT
    if driver.splitlines().count(old)!=1 or 'XIT10 TOP PB VDDIO VDDIO sky130_fd_pr__pfet_g5v0d10v5 w=20 l=1' not in driver.splitlines():raise ValueError('Require the corrected 110:1 restoration driver')
    block=text_block(source,SHIFT);new=SHIFT+'_'+variant
    for branch,inn,out in [(0,'L','Q'),(1,'R','QB')]:
        anchor=f'XB{branch} {inn} {out} VDDIO VSS lvds_inv33_restore_64_24'
        if block.splitlines().count(anchor)!=1:raise ValueError('Original restoration branch changed')
        chain=[inn,f'G{branch}_0',f'G{branch}_1',out];rows=[]
        for stage,count in enumerate(VARIANTS[variant]):
            rows += [f'XB{branch}_S{stage}_{i} {chain[stage]} {chain[stage+1]} VDDIO VSS {UNIT}' for i in range(count)]
        block=block.replace(anchor,'\n'.join(rows))
    block=block.replace(SHIFT,new)
    unit=(f'.subckt {UNIT} A Y VDD VSS\n'
        'XP Y A VDD VDD sky130_fd_pr__pfet_g5v0d10v5 w=16 l=0.5\n'
        'XN Y A VSS VSS sky130_fd_pr__nfet_g5v0d10v5 w=8 l=0.5\n'
        f'.ends {UNIT}\n')
    # Three inversions retain each original branch's logical polarity. The
    # original converter remains captured unchanged, but is no longer bound.
    return replace(source,TOP,driver.replace(old,old.rsplit(' ',1)[0]+' '+new))+'\n'+unit+'\n'+block+'\n'
