# SPDX-License-Identifier: GPL-3.0-only
"""Trip-referenced differential restoration for the qualified N8 decision stage."""
import receiver_gain_balance as baseline
import receiver_lvt_pair_experiment as original
from dll_campaign import text_block
from layout import circuits
from receiver_lvt_restore_experiment import HELPER
from spice_library import replace

TOP = 'openlvds_receiver_core'
VARIANTS = ['control', 'track_t8_r7', 'track_t16_r7']
AMPLIFIER = ['XAT', 'XA0', 'XA1', 'XAD', 'XAM']
RES = 'sky130_fd_pr__res_high_po_0p35'


def source_variant(canonical, variant):
    return transform(baseline.transform(original.source_variant(canonical,True),'control'),variant)


def transform(source, variant):
    if variant not in VARIANTS:
        raise ValueError('Select a declared trip-referenced restoration experiment')
    definitions = circuits(source); rows = {r[0]:r for r in definitions[TOP][1]}
    if (rows['XIB0'][1:3] != (['CO','RESTORE0','VDDD','VSS'],HELPER) or
            any(name in rows for name in AMPLIFIER) or any(name.startswith('XRFB') for name in rows) or
            any(rows[n][3].get('w') != '8' for n in ['XC0','XC1'])):
        raise ValueError('Require the unchanged source-qualified N8 control, not a modified receiver')
    if variant == 'control':
        return source
    drive = rows['XIB1'][2]; track = rows['XTRACK'][2]
    inv = {r[0]:r for r in definitions[drive][1]}; replica = {r[0]:r for r in definitions[track][1]}
    for name,model,width in [('XP','sky130_fd_pr__pfet_01v8',16),('XN','sky130_fd_pr__nfet_01v8',8)]:
        if (inv[name][2] != model or replica[name][2] != model or
                float(inv[name][3]['w']) != width or float(replica[name][3]['w']) != 2*width or
                inv[name][3]['l'] != replica[name][3]['l']):
            raise ValueError('First restoring inverter must match the trip-replica model and width ratio')
    scale = 1 if variant == 'track_t8_r7' else 2
    block = text_block(source,TOP)
    anchor = f'XIB0 CO RESTORE0 VDDD VSS {HELPER}'
    if block.splitlines().count(anchor) != 1:
        raise ValueError('Unexpected original first-restorer binding')
    # CO > CL steers the diode branch, mirrors a sourcing current into
    # AMP_OUT, and lowers RESTORE0 through the matched standard inverter.
    # The two remaining restoring inverters retain the original Q polarity.
    amplifier = '\n'.join([
        f'XAT AMP_CT NBC VSS VSS sky130_fd_pr__nfet_01v8 w={8*scale} l=0.5',
        f'XA0 AMP_L CO AMP_CT VSS sky130_fd_pr__nfet_01v8_lvt w={8*scale} l=0.15',
        f'XA1 AMP_OUT CL AMP_CT VSS sky130_fd_pr__nfet_01v8_lvt w={8*scale} l=0.15',
        f'XAD AMP_L AMP_L VDDD VDDD sky130_fd_pr__pfet_01v8 w={4*scale} l=0.15',
        f'XAM AMP_OUT AMP_L VDDD VDDD sky130_fd_pr__pfet_01v8 w={4*scale} l=0.15'])
    feedback = '\n'.join(f'XRFB{i} AMP_OUT CO_TRACK VSS {RES} w=0.35 l=1.25' for i in range(7))
    replacement = ('* Differential current output is shunted to the inverter trip replica.\n'
        '* Seven original precision-poly units are in parallel; no ideal amplifier.\n'
        +amplifier+'\n'+feedback+f'\nXIB0 AMP_OUT RESTORE0 VDDD VSS {drive}')
    block = block.replace(anchor,replacement)
    return replace(source,TOP,block)
