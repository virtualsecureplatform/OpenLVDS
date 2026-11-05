#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prove the complete repaired bank's native leaf network before CAD integration."""
import argparse
import hashlib
import json
from pathlib import Path
import probe_weighted_direct_v4 as candidate
import assemble_weighted_bank_v2 as assembly
import weighted_bank_physical_v2 as bank

ROOT=candidate.ROOT
sha=candidate.sha
VERSION='complete-repaired-weighted-bank-native-network-v2.1'
CONTEXT='weighted_bank_repair_network_v2'


def calculate(parent,original):
    m=candidate.bound(parent);i=m['identity'];am=assembly.bound(original);ai=am['identity']
    prior=json.loads((ROOT/ai['parent']/'manifest.json').read_text())['identity']
    if any(i[k]!=prior[k] for k in ['compound','fine_cells','clock']):raise ValueError('Unexpected unchanged bank component family replacement')
    modules,orders,devices,paths=candidate.libraries(ROOT/i['compound'],ROOT/i['guard'],ROOT/i['fine_cells'],ROOT/i['repair'],ROOT/i['clock'],Path(i['source_library']))
    if (any((parent/n).read_text()!=text for n,text in modules.items()) or orders!=i['orders'] or devices!=i['devices']):
        raise ValueError('Repaired full-bank source regeneration failed')
    shared=ROOT/ai['shared'];plate=shared/(assembly.shared.NAME+'.sch.spice')
    library=modules['cells.spice']+plate.read_text();source=(original/'bank.spice').read_text()
    native=bank.leaves(library+modules['guarded.spice'],candidate.circuit.NAME)
    physical=bank.leaves(library+source,bank.NAME)
    if physical!=native:raise ValueError('Repaired physical hierarchy changed native R/C/MOS/MIM connections, parameters or multiplicities')
    spec=candidate.circuit.core_instances('guarded')
    if source.count('\nX')!=94 or len(spec)!=78:raise ValueError('Full coarse/fine hierarchy changed')
    guard=json.loads((ROOT/i['guard']/'manifest.json').read_text())['identity']['parent']
    repair=json.loads((ROOT/i['repair']/'manifest.json').read_text())['identity']['parent']
    counts={kind:sum(n for key,n in native.items() if key[0]==kind) for kind in ['R','C','X']}
    proof=dict(native_network_equivalence_passed=True,instances=94,public_ports=24,leaf_counts=counts,
        complete_leaf_multiset_sha256=hashlib.sha256(json.dumps(sorted(native.items())).encode()).hexdigest(),
        guard_physical=guard,repair_physical=repair)
    paths += [parent/'manifest.json',*[parent/n for n in m['libraries']],*[ROOT/n for n in i['inputs']],
              original/'manifest.json',original/'summary.json',original/'bank.spice',plate,
              Path(__file__),Path(candidate.__file__),Path(assembly.__file__),Path(bank.__file__)]
    return proof,paths


def verify(parent,original):
    proof,files=calculate(parent,original)
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),original_assembly=str(original.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    candidate.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    candidate.atomic(out/'summary.json',dict(proof=proof,passed=True,qualified_phy=False,electrical_qualification_passed=False,
        scope='Complete native leaf multiset of staged repaired bank versus full physical root hierarchy; no control-gate admission, intercell routes, whole-bank RC, timing, ROM or PHY qualification'))
    bound(out);return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or not r['passed']):raise ValueError('Repaired bank network receipt changed')
    proof,_=calculate(ROOT/i['parent'],ROOT/i['original_assembly'])
    if r['proof']!=proof:raise ValueError('Full native repaired bank network proof changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('original_assembly',type=Path);a=p.parse_args();print(verify(a.parent.resolve(),a.original_assembly.resolve()),flush=True)
