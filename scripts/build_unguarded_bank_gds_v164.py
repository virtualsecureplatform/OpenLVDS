#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Integrate only the qualified unguarded final output into native routed b2 GDS."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import build_measured_balanced_gds_v150 as stock
import build_unguarded_output_cell_v162 as component
import build_parallel_output_cell_v111 as physical
import unguarded_bank_variant_v164 as variant

ROOT=stock.ROOT
sha=stock.sha
VERSION='whole-bank-local-unguarded-output-native-geometry-v164.1'
CONTEXT='unguarded_bank_gds_v164'
SCOPE='Original routed b2 bank with only the final parallel output MIM guards removed; unchanged coarse regenerators, all native MOS and routed wiring, fresh native DRC/LVS; joint RC, electrical timing and PHY unqualified'


def sources(parent,replacement):
    si,pi=stock.bound(parent);s=json.loads((parent/'summary.json').read_text())
    component.bound(replacement);r=json.loads((replacement/'summary.json').read_text())
    if (not s['native_routed_gds_passed'] or not r['component_physical_rc_passed']
        or any(sha(parent/n)!=h for n,h in s['files'].items()) or any(sha(replacement/n)!=h for n,h in r['files'].items())
        or any(sha(ROOT/n)!=h for n,h in r['extracted_files'].items())):
        raise ValueError('Require unchanged passing original bank and qualified replacement component')
    position=pi['plan']['placements']['u_fine_compound']
    text=(parent/'native'/(variant.TOP+'.sch.spice')).read_text();reference,proof=variant.schematic(text)
    return si,pi,s,r,position,reference,proof


def prepare(parent,replacement):
    si,pi,s,r,position,reference,proof=sources(parent,replacement)
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',*[parent/n for n in s['files']],
           replacement/'manifest.json',replacement/'summary.json',replacement/'state.json',*[replacement/n for n in r['files']]]
    paths += [ROOT/n for n in {**si['inputs'],**json.loads((replacement/'manifest.json').read_text())['identity']['inputs']}]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),replacement=str(replacement.relative_to(ROOT)),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},position=position,
           graph=dict(pi['graph'],top=variant.NEW_TOP),plan=pi['plan'],reference=reference,native_revision_proof=proof,
           scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Unguarded whole-bank context changed')
    si,pi,s,r,pos,ref,proof=sources(ROOT/i['parent'],ROOT/i['replacement'])
    if pos!=i['position'] or ref!=i['reference'] or proof!=i['native_revision_proof']:raise ValueError('Whole-bank revision does not regenerate')
    return i,s,r


def run(out):
    i,s,r=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial native bank revision')
        (out/'state.json').write_text('{"status":"qualifying","qualified_phy":false}\n')
        source=ROOT/s['physical']['gds'];candidate=out/'candidate.gds'
        masks=variant.geometry(source,candidate,i['position'])
        qualified_component=variant.component_match(candidate,ROOT/r['physical']['gds'])
        result,params=physical.qualify(out,candidate,i['graph'],i['plan'],i['reference'])
        expected_ports,expected=variant.inventory.native_leaves(i['reference'],variant.NEW_TOP)
        extracted=re.sub(r'\n[ \t]*\+[ \t]*',' ',(out/'native'/(variant.NEW_TOP+'.lvs.spice')).read_text())
        actual_ports,actual=variant.inventory.native_leaves(extracted,variant.NEW_TOP+'_flat')
        if expected_ports!=actual_ports or params['native_primitives']!=1493:raise ValueError('Whole-bank port order or 1453-MOS/40-MIM inventory changed')
        final_masks=variant.mask_check(source,ROOT/result['gds'],i['position'])
        final_component=variant.component_match(ROOT/result['gds'],ROOT/r['physical']['gds'])
        bound(out)
        report=dict(native_routed_gds_passed=True,physical=result,native_parameters=params,
            native_revision_proof=i['native_revision_proof'],mask_proof=masks,final_mask_proof=final_masks,
            qualified_component_proof=qualified_component,final_qualified_component_proof=final_component,
            original_routed_wiring_retained=True,new_global_route_required=False,joint_rc_extracted=False,
            electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--replacement',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.replacement is None:p.error('--replacement required')
        out=prepare(out,a.replacement.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
