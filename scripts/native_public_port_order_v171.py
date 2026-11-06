# SPDX-License-Identifier: GPL-3.0-only
"""Restore a bijective named public-port order without touching circuit body bytes."""
import native_clock_components_v2 as native
import native_bank_inventory_v51 as inventory
import measured_bank_junction_reconstruction_v142 as cards


def canonicalize(text,top,ports):
    definitions=native.definitions(text)
    if set(definitions)!={top}:raise ValueError('Require exactly one flat native definition')
    before,body=definitions[top]
    if (not ports or len(set(before))!=len(before) or len(set(ports))!=len(ports)
        or len(before)!=len(ports) or set(before)!=set(ports)):
        raise ValueError('Public port lists must be an exact named bijection')
    lines=text.splitlines(keepends=True)
    starts=[k for k,line in enumerate(lines) if line.lstrip().lower().startswith('.subckt ')]
    if len(starts)!=1:raise ValueError('Require one unambiguous public header')
    start=starts[0];end=start+1
    while end<len(lines) and lines[end].lstrip().startswith('+'):end+=1
    result=text if before==ports else ''.join(lines[:start])+'.subckt '+top+' '+' '.join(ports)+'\n'+''.join(lines[end:])
    after=native.definitions(result)
    if after!={top:(ports,body)} or cards.passive_lines(result)!=cards.passive_lines(text):raise ValueError('Port adapter changed a device or passive statement')
    _,a=inventory.native_leaves(cards.collapse(text),top);_,b=inventory.native_leaves(cards.collapse(result),top)
    if a!=b:raise ValueError('Port adapter changed a named native device/net/parameter')
    if before!=ports:
        suffix=''.join(lines[end:]);prefix=''.join(lines[:start])
        if not result.startswith(prefix) or not result.endswith(suffix):raise ValueError('Non-header bytes changed')
    return result,dict(original_ports=before,canonical_ports=ports,header_changed=before!=ports,
        named_public_port_bijection_verified=True,all_device_nodes_models_parameters_identical=True,
        all_nonheader_bytes_preserved=True,passive_records_byte_identical=True,qualified_phy=False)
