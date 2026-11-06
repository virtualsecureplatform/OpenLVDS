# SPDX-License-Identifier: GPL-3.0-only
"""Reconstruct only the 62 identified fine-capacitor junctions in a flat bank.

Callers must bind the actual primitive masks/separate active regions to the
isolated measurements. Electrical use additionally requires routed native LVS
and qualification of the original and corrected joint RC. This helper proves
neither geometric provenance nor bank LVS on its own.
"""
from collections import Counter
import re
import measured_bank_fine_partition_v139 as fine
import measured_bank_native_inventory_v138 as census
from audit_rc_comments_v2 import collapse as collapse_wires

FIELDS=fine.junctions.FIELDS


def collapse(text):
    # Normalize continuations for analysis only; source/output bytes stay intact.
    data='\n'.join(line.split('$',1)[0] for line in text.splitlines())+'\n'
    return collapse_wires(re.sub(r'\n[ \t]*\+[ \t]*',' ',data))


def signature(text,top):
    ports,devices=fine.native.native_leaves(collapse(text),top)
    return ports,Counter(map(fine.junctions.topology_key,devices))


def passive_lines(text):
    return [line for line in text.splitlines(keepends=True) if line.lstrip().startswith(('R','r','C','c'))]


def records(text):
    """Locate native MOS cards, retaining byte offsets and SPICE continuations."""
    lines=text.splitlines(keepends=True);offsets=[];offset=0
    for line in lines:offsets.append(offset);offset+=len(line)
    offsets.append(offset);result={}
    for k,line in enumerate(lines):
        words=line.split()
        if not words or not words[0].lower().startswith('x'):continue
        name=words[0]
        if name in result:raise ValueError('Duplicate native instance card')
        end=k+1
        while end<len(lines) and lines[end].lstrip().startswith('+'):end+=1
        result[name]=(offsets[k],offsets[end])
    return result


def reconstruct(text,top,measurement_rows,profile):
    definitions=re.findall(r'(?im)^\s*\.subckt\s+(\S+)',text)
    if definitions!=[top]:raise ValueError('Require one flat bank namespace before junction reconstruction')
    collapsed=collapse(text);partition=fine.identify(collapsed,top)
    ports,before=fine.native.native_leaves(collapsed,top);lookup={d['name']:d for d in before}
    library=fine.junctions.junction_library(measurement_rows);cards=records(text);updates=[];cap_names=set()
    for section in partition['sections']:
        for role in ['capacitor_n','capacitor_p']:
            device=lookup[section[role]];key=fine.junctions.geometry_key(device)
            if key not in library:raise ValueError('Missing isolated fine capacitor measurement')
            target=library[key]['values']
            if any(fine.native.exact_number(target[a])!=fine.native.exact_number(target[b]) for a,b in [('ad','as'),('pd','ps')]):
                raise ValueError('Tied D/S orientation requires symmetric measured junctions')
            original={f:device['params'].get(f) for f in FIELDS}
            if any(v is None or fine.native.exact_number(v)<0 for v in original.values()):raise ValueError('Invalid original capacitor junction fields')
            name=device['name'].removeprefix('native__')
            if name not in cards:raise ValueError('Native capacitor does not map to one flat source card')
            start,end=cards[name];card=text[start:end];changed={}
            for field in FIELDS:
                pattern=r'(?<!\S)'+field+r'=([^\s$]+)'
                # Ignore inline comments without changing their bytes.
                occurrences=[];cursor=0
                for line in card.splitlines(keepends=True):
                    data=line.split('$',1)[0]
                    for match in re.finditer(pattern,data):occurrences.append((cursor+match.start(1),cursor+match.end(1),match[1]))
                    cursor+=len(line)
                if len(occurrences)!=1:raise ValueError('Missing or ambiguous native capacitor junction token')
                a,b,value=occurrences[0]
                if fine.native.exact_number(value)!=fine.native.exact_number(original[field]):raise ValueError('Native capacitor token disagrees with parsed extraction')
                if fine.native.exact_number(value)!=fine.native.exact_number(target[field]):
                    card=card[:a]+target[field]+card[b:];changed[field]=dict(before=value,after=target[field])
            cap_names.add(device['name'])
            updates.append(dict(instance=name,primitive=library[key]['cell'],role=role,cap_node=section['cap_node'],
                                changes=changed,start=start,end=end,card=card))
    corrected=text
    for row in sorted(updates,key=lambda x:x['start'],reverse=True):corrected=corrected[:row['start']]+row['card']+corrected[row['end']:]
    if len(cap_names)!=62 or signature(text,top)!=signature(corrected,top):raise ValueError('Capacitor repair changed native topology/model/dimensions')
    if passive_lines(text)!=passive_lines(corrected):raise ValueError('Capacitor repair changed a passive record')
    _,after=fine.native.native_leaves(collapse(corrected),top)
    before_noncap=[d for d in before if d['name'] not in cap_names];after_noncap=[d for d in after if d['name'] not in cap_names]
    if before_noncap!=after_noncap:raise ValueError('Capacitor repair changed a non-capacitor device or parameter')
    diagnostic=fine.diagnose(collapse(corrected),top,measurement_rows)
    if not diagnostic['per_device_capacitor_junctions_match_geometry']:raise ValueError('Capacitor reconstruction does not reproduce measured junctions')
    native=census.verify(collapse(corrected),top,collapse(corrected),top,profile)
    proof=dict(native_census=native,identified_capacitor_mos=62,corrected_devices=sum(bool(r['changes']) for r in updates),
               corrected_fields=sum(len(r['changes']) for r in updates),
               corrections=[{k:v for k,v in r.items() if k not in ['start','end','card']} for r in updates if r['changes']],
               all_noncapacitor_devices_and_parameters_unchanged=True,all_native_topology_and_dimensions_unchanged=True,
               passive_records_byte_identical=True,passive_record_count=len(passive_lines(text)),
               measured_geometry_provenance_required=True,whole_bank_native_lvs_required=True,
               joint_rc_qualified=False,electrical_qualification_passed=False,qualified_phy=False)
    return corrected,proof
