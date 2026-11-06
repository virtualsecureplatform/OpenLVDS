#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete joint-RC proof from retained extraction after v144 parser failure.

Preserves every original file; normalizes continuations in analysis views only.
All native geometry, junction, passive, LVS and Schur gates remain mandatory.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import verify_measured_balanced_joint_rc_v144 as previous
import measured_native_parameter_view_v155 as parameter_view
import build_measured_balanced_gds_v150 as physical
import analyze_measured_bank_fine_junctions_v140 as geometry
import measured_bank_junction_reconstruction_v142 as correction
import extract_native_flat_v4 as extractor
import verify_tg_bank_joint_rc_v52 as mathematics
from audit_passive_rc_v3 import audit
from reduce_rc import reduce_netlist
from lvs_utils import strict_setup,clean_match

ROOT=physical.ROOT
sha=physical.sha
VERSION='measured-balanced-retained-actual-joint-rc-continuation-safe-native-proof-v155.1'
CONTEXT='measured_balanced_joint_rc_v155'


def inputs(parent,evidence):
    pi,bi=physical.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['native_routed_gds_passed'] or not r['physical']['passed']
        or r['physical']['drc_count']!='0' or not r['physical']['lvs_passed']
        or not r['native_parameters']['native_parameters_preserved']
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require complete unchanged routed native GDS DRC/LVS and parameters')
    gi,_=geometry.bound(evidence);gr=json.loads((evidence/'summary.json').read_text())
    if (json.loads((evidence/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or not gr['analysis_completed'] or gr['geometry']!=gi['geometry']
        or any(sha(evidence/n)!=h for n,h in gr['files'].items())
        or gi['parent']!=pi['placement'] or gi['profile']!=pi['profile']):
        raise ValueError('Fine primitive geometry belongs to a different placement/profile')
    if gr['geometry']['fine_instances']!=31 or not gr['geometry']['measured_primitive_junction_geometry_bound']:
        raise ValueError('Require complete measured fine primitive geometry')
    top=bi['graph']['top'];gds=parent/(top+'.gds')
    if physical.native_cells(gds,ROOT/pi['placement'],bi)!=r['native_hierarchy_proof']:
        raise ValueError('Actual routed native masks/hierarchy/placements changed')
    return pi,bi,r,gr,gds


def retained(failed):
    # A live producer owns this lock; never consume or restart its partial work.
    with (failed/'.execution.lock').open('r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old,bi=previous.bound(failed)
        if json.loads((failed/'state.json').read_text())!=dict(status='extracting',qualified_phy=False):
            raise ValueError('Require the retained incomplete v144 extraction')
        parent=ROOT/old['parent'];gds=ROOT/old['gds'];top=old['top']
        digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
        namespace=ROOT/'build/extracted'/digest[:16]/top
        info=json.loads((namespace/'summary.json').read_text())
        if (not info['passed'] or info['returncode']!=0 or not info['ports_verified'] or info['ports']!=bi['graph']['ports']
            or info['fingerprint']!=digest or info['gds_sha256']!=sha(gds)
            or info['source_sha256']!=sha(parent/'manifest.json') or info['source_scope_sha256']!=sha(parent/'native'/(top+'.lvs.spice'))
            or info['passivity']!=audit((ROOT/info['raw_netlist']).read_text())
            or sha(ROOT/info['raw_netlist'])!=info['reduction']['source_sha256'] or sha(ROOT/info['netlist'])!=info['netlist_sha256']):
            raise ValueError('Retained extraction does not bind the qualified native GDS')
        return old,bi,info,{str(p.relative_to(ROOT)):sha(p) for p in namespace.rglob('*') if p.is_file()}


def prepare(failed):
    old,bi,info,files=retained(failed)
    paths=[p for p in failed.rglob('*') if p.is_file()]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(old,version=VERSION,source_partial=str(failed.relative_to(ROOT)),original_info=info,original_extraction_files=files,
           inputs={**old['inputs'],**files,**{str(p.relative_to(ROOT)):sha(p) for p in paths}},
           scope='Retained actual routed whole-bank RC, analysis-only continuation normalization, measured junction repair, native parameters/topology, exact reduction and independent Schur witness; no transient/PVT/PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or mathematics.math_proof()['runtime']!=i['math_runtime']):raise ValueError('Measured routed joint RC context changed')
    old,bi,info,files=retained(ROOT/i['source_partial'])
    if info!=i['original_info'] or files!=i['original_extraction_files']:raise ValueError('Retained original extraction changed')
    pi,bi,_,_,gds=inputs(ROOT/i['parent'],ROOT/i['geometry'])
    if pi['placement']!=i['placement'] or pi['profile']!=i['profile'] or str(gds.relative_to(ROOT))!=i['gds']:
        raise ValueError('Measured joint RC bank identity changed')
    return i,bi



def fine_junctions(text,top,rows):
    collapsed=correction.collapse(text);partition=correction.fine.identify(collapsed,top)
    _,devices=correction.fine.native.native_leaves(collapsed,top);lookup={d['name']:d for d in devices}
    library=correction.fine.junctions.junction_library(rows);count=0
    for section in partition['sections']:
        for role in ['capacitor_n','capacitor_p','pass_n','pass_p','clear']:
            device=lookup[section[role]];key=correction.fine.junctions.geometry_key(device)
            if key not in library:raise ValueError('Missing measured fine primitive')
            target=library[key]['values']
            if any(correction.fine.native.exact_number(target[a])!=correction.fine.native.exact_number(target[b]) for a,b in [('ad','as'),('pd','ps')]):
                raise ValueError('Fine primitive junction orientation needs additional geometric proof')
            if any(f not in device['params'] or correction.fine.native.exact_number(device['params'][f])!=correction.fine.native.exact_number(target[f]) for f in correction.FIELDS):
                raise ValueError('Fine device junctions differ from measured geometry: '+role)
            count+=1
    if count!=155:raise ValueError('Fine primitive geometry coverage changed')
    return dict(fine_mos_with_all_measured_junction_fields=155,capacitor_mos=62,programming_mos=93)


def run(out):
    i,bi=bound(out);parent=ROOT/i['parent'];top=i['top'];gds=ROOT/i['gds']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial measured joint RC qualification')
        (out/'state.json').write_text('{"status":"extracting","qualified_phy":false}\n')
        native=parent/'native'/(top+'.lvs.spice')
        digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
        namespace=ROOT/'build/extracted'/digest[:16]/top
        if not namespace.is_dir():raise ValueError('Retained original extraction is missing')
        info=i['original_info']
        if (not info['passed'] or info['returncode']!=0 or not info['ports_verified'] or info['ports']!=bi['graph']['ports']
            or info['fingerprint']!=digest or info['gds_sha256']!=sha(gds)
            or info['source_sha256']!=sha(parent/'manifest.json') or info['source_scope_sha256']!=sha(native)):
            raise ValueError('Actual routed whole-bank RC extraction failed its input/interface/passivity gate')
        original_files=i['original_extraction_files']
        raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist']
        if sha(raw)!=info['reduction']['source_sha256'] or sha(reduced)!=info['netlist_sha256']:
            raise ValueError('Original extraction hashes changed')
        if reduce_netlist(raw,out/'original_regenerated.spice')!=info['reduction'] or sha(out/'original_regenerated.spice')!=info['netlist_sha256']:
            raise ValueError('Original passive reduction does not regenerate exactly')
        rows=json.loads((geometry.MEASUREMENTS/'summary.json').read_text())['rows']
        original=raw.read_text();ordinary=native.read_text()
        corrected,raw_proof=correction.reconstruct(original,top,rows,i['profile'])
        measured,reference_proof=correction.reconstruct(ordinary,top+'_flat',rows,i['profile'])
        target=out/'corrected';target.mkdir();raw_path=target/'raw.spice';ref_path=target/'measured_reference.spice';netlist=target/'reduced.spice'
        raw_path.write_text(corrected);ref_path.write_text(measured)
        if raw_proof['passive_record_count']==0:raise ValueError('Joint RC correction has no actual passive elements')
        passivity={label:audit(text) for label,text in [('original_raw',original),('corrected_raw',corrected)]}
        if not all(p['elementwise_passive_passed'] for p in passivity.values()):raise ValueError('Original or corrected native RC is not elementwise passive')
        reduction=reduce_netlist(raw_path,netlist);passivity['corrected_reduced']=audit(netlist.read_text())
        if not passivity['corrected_reduced']['elementwise_passive_passed']:raise ValueError('Corrected reduced RC is not elementwise passive')
        if reduce_netlist(raw_path,target/'regenerated.spice')!=reduction or sha(target/'regenerated.spice')!=sha(netlist):
            raise ValueError('Corrected passive reduction does not regenerate exactly')
        collapsed=target/'wire_collapsed.spice';collapsed.write_text(correction.collapse(netlist.read_text()))
        parameters=parameter_view.verify(measured,top+'_flat',collapsed.read_text(),top,i['profile'])
        fine_parameters=dict(reference=fine_junctions(measured,top+'_flat',rows),joint_rc=fine_junctions(collapsed.read_text(),top,rows))
        setup=strict_setup(target/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        result=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {top}',f'{ref_path} {top}_flat',str(setup),str(target/'lvs.log')],cwd=target,capture_output=True,text=True)
        (target/'lvs_console.log').write_text(result.stdout+result.stderr)
        if not clean_match((target/'lvs.log').read_text(),result.returncode):raise ValueError('Corrected joint RC differs from actual routed native topology')
        proof=mathematics.math_proof(raw_path,netlist)
        (target/'schur_witness.json').write_text(json.dumps(proof,indent=2)+'\n')
        if proof['runtime']!=i['math_runtime'] or not proof['proof']['passed']:raise ValueError('Corrected joint RC terminal-current witness failed')
        if correction.reconstruct(original,top,rows,i['profile'])!=(corrected,raw_proof):raise ValueError('Actual RC junction correction does not regenerate')
        again,idempotence=correction.reconstruct(corrected,top,rows,i['profile'])
        if again!=corrected or idempotence['corrected_devices']!=0:raise ValueError('Actual RC junction correction is not byte-idempotent')
        if any(sha(ROOT/n)!=h for n,h in original_files.items()):raise ValueError('Original extraction was changed')
        bound(out)
        final=dict(info,raw_netlist=str(raw_path.relative_to(ROOT)),netlist=str(netlist.relative_to(ROOT)),netlist_sha256=sha(netlist),reduction=reduction,junctions_reconstructed_from_native_masks=True)
        r=dict(joint_rc_passed=True,extraction=final,original_extraction=info,original_extracted_files=original_files,
               original_extraction_preserved=True,raw_junction_correction=raw_proof,native_reference_correction=reference_proof,
               native_parameters=parameters,all_fine_junctions=fine_parameters,native_topology_verified=True,passivity=passivity,
               original_and_corrected_reductions_regenerated=True,independent_terminal_current_witness=proof['proof'],
               capacitance_threshold_ff=.01,electrical_qualification_passed=False,qualified_phy=False,scope=i['scope'])
        r['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
