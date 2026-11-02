# SPDX-License-Identifier: GPL-3.0-only
"""Match the loaded trip reference using exact parallel first-inverter units."""
import receiver_differential_restore as previous
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP=previous.TOP
AMPLIFIER=previous.AMPLIFIER
RES=previous.RES
VARIANTS=['control','matched_t8_r7','matched_t16_r7']
HELPER='lvds_rx_track_matched'


def source_variant(canonical,variant):
    base=previous.baseline.transform(previous.original.source_variant(canonical,True),'control')
    return transform(base,variant)


def transform(source,variant):
    if variant not in VARIANTS:raise ValueError('Select a declared unit-matched trip restoration experiment')
    mapped=dict(control='control',matched_t8_r7='track_t8_r7',matched_t16_r7='track_t16_r7')[variant]
    source=previous.transform(source,mapped)
    if variant=='control':return source
    definitions=circuits(source);rows={r[0]:r for r in definitions[TOP][1]}
    if HELPER in definitions or rows['XTRACK'][1]!=['CO_TRACK','CO_TRACK','VDDD','VSS']:
        raise ValueError('Unexpected original loaded trip reference')
    drive=rows['XIB0'][2];ports,devices=definitions[drive]
    if ports!=['A','Y','VDD','VSS'] or [r[0] for r in devices]!=['XP','XN']:
        raise ValueError('Require the exact two-device first restoring inverter')
    helper=text_block(source,drive).splitlines();lines=['.subckt '+HELPER+' '+' '.join(ports)]
    for name,_,_,_ in devices:
        line=next(line for line in helper if line.startswith(name+' '))
        for index in [0,1]:lines.append(name+str(index)+line[len(name):])
    lines.append('.ends '+HELPER)
    old='XTRACK CO_TRACK CO_TRACK VDDD VSS '+rows['XTRACK'][2]
    block=text_block(source,TOP)
    if block.splitlines().count(old)!=1:raise ValueError('Unexpected trip-reference binding')
    block=block.replace(old,'XTRACK CO_TRACK CO_TRACK VDDD VSS '+HELPER)
    return replace(source,TOP,block)+'\n'+'\n'.join(lines)+'\n'
