#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Unqualified, topology-only interventions for fast-entry electrical failures."""
from copy import deepcopy
import tg2_p40n32_bank_300 as source
import native_clock_components_v2 as native

VERSION='qualified-unit-fast-entry-damping-bank-300-v1'
KINDS=('coarse_shunt','decode_drive2','combined')
COARSE='openlvds_balanced_coarse_v352'


def transform(library,top,observations,kind):
    if kind not in KINDS:raise ValueError('Unknown fast-entry intervention')
    defs=native.definitions(library);ports,body=defs[top]
    coarse_ports,coarse_body=defs[COARSE]
    expected=[['Xa','IN','mid','VPWR','VGND','openlvds_parallel_inv8_v110'],
              ['Xb','mid','OUT','VPWR','VGND','openlvds_parallel_inv8_v110']]
    if coarse_ports!=['IN','OUT','VPWR','VGND'] or coarse_body!=expected:
        raise ValueError('Original balanced coarse topology changed')
    calls={f'Xdelay{k}' for k in range(1,16)}|{'Xtail_load'}
    if {w[0] for w in body if w[-1]==COARSE}!=calls:
        raise ValueError('Require every coarse stage and retained tail termination')
    pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports}
    before=native.mapped_mos(library,top,pins,'XD')
    if before!=observations['devices']:raise ValueError('Original full native map changed')
    shunt=kind in ('coarse_shunt','combined');boost=kind in ('decode_drive2','combined')
    new_top=top+'_fast_'+kind;new_coarse='openlvds_coarse_mid_shunted_300_v1'
    if new_top in defs or (shunt and new_coarse in defs):raise ValueError('Retain prior intervention')
    additions=[];changed=deepcopy(body)
    if shunt:
        if source.SOURCE.definition(library,source.MODEL)!=source.qualified_cell():
            raise ValueError('Require the exact physically qualified double-TG MIM unit')
        # The existing extracted TG/MIM unit is held on: EN=VPWR, ENB=VGND.
        # Its clamp is held off. No new device model or ideal fitted C is used.
        additions=['.subckt '+new_coarse+' '+' '.join(coarse_ports),
                   *[' '.join(w) for w in coarse_body],
                   'Xdamp mid VPWR VGND VPWR VGND '+source.MODEL,'.ends '+new_coarse,'']
        changed=[w[:-1]+[new_coarse] if w[0] in calls else w for w in changed]
    inverse={f'Xdecode_inverse{stage}_{k}' for stage in range(2) for k in range(4)}
    drivers=[w for w in body if w[0] in inverse]
    if len(drivers)!=8 or any(w[-1]!='sky130_fd_sc_hd__inv_4' for w in drivers):
        raise ValueError('Original decoded ENB drivers changed')
    if boost:
        changed += [[w[0]+'_boost',*w[1:]] for w in drivers]
    additions += ['.subckt '+new_top+' '+' '.join(ports),*[' '.join(w) for w in changed],'.ends '+new_top,'']
    result=library+'\n'+'\n'.join(additions)
    devices=native.mapped_mos(result,new_top,pins,'XD');actual={d['name']:d for d in devices}
    if len(actual)!=len(devices) or any(actual.get(d['name'])!=d for d in before):
        raise ValueError('Existing transistor terminal maps, models or limits changed')
    gates=deepcopy(observations['programming_gates'])
    if any(actual[g['device']]['terminals'][1]!=g['gate_node'] for g in gates):
        raise ValueError('Existing programmable-gate observations changed')
    # Extra shunt gates are tied rails, not programmable signals. Every added
    # MOS terminal remains included in the full native electrical envelope.
    return result,new_top,dict(devices=devices,controls=deepcopy(observations['controls']),programming_gates=gates),dict(
        version=VERSION,kind=kind,coarse_shunt_units=16 if shunt else 0,decode_inverse_boosters=8 if boost else 0,
        shunt_component=source.MODEL if shunt else None,shunt_enable='VPWR' if shunt else None,
        shunt_disable='VGND' if shunt else None,native_mos=len(devices),qualified_phy=False,
        scope='Unqualified whole-bank intervention; timing, update, parity, common RC and PVT remain required')
