# SPDX-License-Identifier: GPL-3.0-only
"""Use the first restoring inverter as a current-to-voltage amplifier with real resistive feedback."""
import receiver_differential_restore as baseline
from dll_campaign import text_block
from layout import circuits
from receiver_lvt_restore_experiment import HELPER
from spice_library import replace

TOP=baseline.TOP
RES=baseline.RES
AMPLIFIER=[]
VARIANTS=['control','tia_r2','tia_r4']


def source_variant(canonical,variant):
    source=baseline.baseline.transform(baseline.original.source_variant(canonical,True),'control')
    return transform(source,variant)


def transform(source,variant):
    if variant not in VARIANTS:raise ValueError('Select a declared feedback-inverter receiver experiment')
    source=baseline.transform(source,'control')
    if variant=='control':return source
    definitions=circuits(source);rows={r[0]:r for r in definitions[TOP][1]}
    if any(n.startswith('XRFB') for n in rows):raise ValueError('Feedback path already exists')
    drive=rows['XIB1'][2]
    if drive!='lvds_inv18_drive':raise ValueError('Require the original standard restoring inverter')
    anchor=f'XIB0 CO RESTORE0 VDDD VSS {HELPER}'
    block=text_block(source,TOP)
    if block.splitlines().count(anchor)!=1:raise ValueError('Unexpected original first-restorer binding')
    count=2 if variant=='tia_r2' else 4
    chain=['CO']+['FB'+str(i) for i in range(1,count)]+['RESTORE0']
    feedback='\n'.join(f'XRFB{i} {chain[i]} {chain[i+1]} VSS {RES} w=0.35 l=1.25' for i in range(count))
    replacement=('* Negative resistive feedback around the first standard inverter.\n'
        '* Original decision current is converted at RESTORE0 with reduced CO swing.\n'
        +f'XIB0 CO RESTORE0 VDDD VSS {drive}\n'+feedback)
    return replace(source,TOP,block.replace(anchor,replacement))
