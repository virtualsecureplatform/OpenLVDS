# SPDX-License-Identifier: GPL-3.0-only
"""Two bounded later-buffer alternatives; keep the original TIA and frontend."""
from dll_campaign import text_block
from spice_library import replace
import receiver_tia_restore as tia

TOP=tia.TOP
VARIANTS=['baseline','symmetric_taper','skewed_buffers']


def transform(source,variant):
    if variant not in VARIANTS:raise ValueError('Select one of the two declared later-buffer alternatives or baseline')
    block=text_block(source,TOP)
    for line in ['XIB1 RESTORE0 RESTORE1 VDDD VSS lvds_inv18_drive',
                 'XIB2 RESTORE1 Q VDDD VSS lvds_inv18_drive']:
        if block.splitlines().count(line)!=1:raise ValueError('Require unchanged original later inverters')
    if not all(f'XRFB{i} ' in block for i in range(2)) or 'XRFB2 ' in block:
        raise ValueError('Require original two-resistor TIA')
    drive=text_block(source,'lvds_inv18_drive')
    if 'XP Y A VDD VDD sky130_fd_pr__pfet_01v8 w=16 l=0.15' not in drive or 'XN Y A VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=0.15' not in drive:
        raise ValueError('Require original unit-device bins')
    if variant=='baseline':return source
    for stage,inn,out in [(1,'RESTORE0','RESTORE1'),(2,'RESTORE1','Q')]:
        if variant=='symmetric_taper':
            count=2 if stage==1 else 4
            rows=[f'XIB{stage}_{j} {inn} {out} VDDD VSS lvds_inv18_drive' for j in range(count)]
        else:
            # One complete original inverter plus only the requested unit device.
            rows=[f'XIB{stage} {inn} {out} VDDD VSS lvds_inv18_drive']
            rows += ([f'XIB1_EXTRA_P {out} {inn} VDDD VDDD sky130_fd_pr__pfet_01v8 w=16 l=0.15'] if stage==1 else
                     [f'XIB2_EXTRA_N {out} {inn} VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=0.15'])
        block=block.replace(f'XIB{stage} {inn} {out} VDDD VSS lvds_inv18_drive','\n'.join(rows))
    return replace(source,TOP,block)
