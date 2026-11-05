#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare actual old/new extracted coupling with native geometry/RC proofs."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path
import wide_guard_pair_rc_families_v2 as old_family
import verify_nand2b_separated_pair_rc_v3 as new_verification
import verify_nand2b_separated_pair_v3 as mask_proof
from weighted_routed_observation_v2 import Groups,MOS,PASSIVE
from native_clock_components_v2 import definitions
from reduce_rc import number
from spice_library import checked_netlist

ROOT=old_family.ROOT
VERSION='native-separated-nand2b-pair-extracted-coupling-comparison-v3.1'
CONTEXT='nand2b_separated_pair_coupling_v3'
sha=old_family.sha


def network(text):
    defs=definitions(text)
    if len(defs)!=1:raise ValueError('Require one flat native pair')
    ports,body=next(iter(defs.values()));expected={'A_N','B','Y','VGND','VPWR'}
    if set(ports)!=expected or len(ports)!=5:raise ValueError('Native pair interface changed')
    groups=Groups();caps=[];models=Counter()
    for port in ports:groups.root(port)
    for row in body:
        row=' '.join(row).split('$',1)[0].split()
        if not row:continue
        kind=row[0][0].upper()
        if kind in ['R','C']:
            if len(row)!=4:raise ValueError('Unknown flat RC statement')
            value=number(row[3])
            if not math.isfinite(value) or value<0 or (kind=='R' and value==0):raise ValueError('Nonpassive RC value')
            if kind=='R':groups.join(row[1],row[2])
            else:caps.append((row[1],row[2],value))
        elif kind=='X':
            end=next((i for i,t in enumerate(row) if '=' in t),len(row));model=row[end-1]
            if model not in MOS|PASSIVE:raise ValueError('Unknown non-native pair primitive')
            models[model]+=1
        else:raise ValueError('Unknown native pair statement')
    if len({groups.root(p) for p in ports})!=5:raise ValueError('Extracted network shorts native public pins')
    labels={groups.root(p):p for p in ports};coupling=defaultdict(float);incident=defaultdict(float)
    for a,b,value in caps:
        a,b=groups.root(a),groups.root(b)
        if a==b:continue
        pa,pb=labels.get(a),labels.get(b)
        if pa:incident[pa]+=value
        if pb:incident[pb]+=value
        if pa and pb:coupling[':'.join(sorted([pa,pb]))]+=value
    return dict(native_primitives=dict(sorted(models.items())),
        port_coupling_ff={k:v*1e15 for k,v in sorted(coupling.items())},
        incident_explicit_parasitic_ff={k:v*1e15 for k,v in sorted(incident.items())})


def compare(original,repaired):
    old,paths=old_family.witnesses(original)
    old_name='openlvds_nand2b_4_o1_stack_guard_pair_v2'
    if set(old)!={old_name}:raise ValueError('Require the exact wide-power native baseline pair')
    nm=new_verification.bound(repaired);ni=nm['identity'];nr=json.loads((repaired/'summary.json').read_text());new_row=nr['rows'][0]
    em=new_verification.extraction.bound(ROOT/ni['extraction']);proof=ROOT/em['identity']['native_proof'];pr=mask_proof.bound(proof,ROOT/ni['parent'])
    om=json.loads((original/'manifest.json').read_text())['identity']
    if pr['identity']['original']!=om['parent']:raise ValueError('Coupling baseline differs from the proven old mask/source pair')
    oi=old[old_name]['info'];new_info=new_row['extraction'];before=network(old[old_name]['text']);after=network(checked_netlist(new_info))
    before_raw=network(checked_netlist(dict(oi,netlist=oi['raw_netlist'],netlist_sha256=oi['reduction']['source_sha256'])))
    after_raw=network(checked_netlist(dict(new_info,netlist=new_info['raw_netlist'],netlist_sha256=new_info['reduction']['source_sha256'])))
    if before!=before_raw or after!=after_raw:raise ValueError('Exact resistor reduction changed net-group coupling/primitive counts')
    if (before['native_primitives']!=after['native_primitives'] or sum(before['native_primitives'].get(m,0) for m in MOS)!=36
        or before['native_primitives'].get('sky130_fd_pr__cap_mim_m3_1')!=4):raise ValueError('Native guard pair transistor/MIM coverage changed')
    old_cap=before['port_coupling_ff'].get('B:Y',0.);new_cap=after['port_coupling_ff'].get('B:Y',0.)
    if not 0<new_cap<old_cap:raise ValueError('Separated routing did not reduce actual extracted B-Y coupling')
    paths += [original/n for n in ['manifest.json','summary.json','state.json']]+[repaired/n for n in ['manifest.json','summary.json','state.json']]
    paths += [ROOT/n for n in {**ni['inputs'],**ni['code']}]+[proof/'summary.json']
    paths += [ROOT/new_info['netlist'],ROOT/new_info['raw_netlist'],Path(__file__),Path(old_family.__file__),Path(new_verification.__file__),Path(mask_proof.__file__),ROOT/'scripts/reduce_rc.py',ROOT/'scripts/weighted_routed_observation_v2.py']
    identity=dict(version=VERSION,original=str(original.relative_to(ROOT)),repaired=str(repaired.relative_to(ROOT)),
        native_mask_proof=str(proof.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Native coupling evidence changed during comparison')
    out.mkdir(parents=True,exist_ok=False);(out/'summary.json').write_text(json.dumps(dict(identity=identity,before=before,after=after,
        original_b_y_ff=old_cap,separated_b_y_ff=new_cap,reduction_percent=100*(1-new_cap/old_cap),
        unchanged_native_primitives=True,raw_and_reduced_network_groups_match=True,extracted_coupling_reduced=True,
        qualified_phy=False,electrical_qualification_passed=False,
        scope='Fresh independently verified physical pair RC and native mask/source/placement proof; reduced explicit parasitic coupling only, no transient voltage, delay, whole-bank or PHY admission'),indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('repaired',type=Path);a=p.parse_args()
    print(compare(a.original.resolve(),a.repaired.resolve()),flush=True)
