#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete retained bank RC after a verified named public-header permutation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import verify_unguarded_bank_joint_rc_v165 as previous
from verify_unguarded_bank_joint_rc_v165 import ROOT,sha,geometry,correction,extractor,mathematics,audit,reduce_netlist,strict_setup,clean_match,fine_junctions,native_parameters
import native_public_port_order_v171 as ports

VERSION='retained-unguarded-b2-joint-rc-canonical-public-header-native-proof-v171.1'
CONTEXT='unguarded_bank_joint_rc_v171'
SCOPE='Retained fresh unguarded bank RC, bijective named public-header restoration with all body bytes intact, selective geometry-bound fine junctions, strict native census/topology/parameters, passive reduction and independent current witness; no transient/PVT/PHY admission'


def retained(failed):
    with (failed/'.execution.lock').open('r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        i,bi=previous.bound(failed)
        if json.loads((failed/'state.json').read_text())!=dict(status='extracting',qualified_phy=False):raise ValueError('Require the retained v165 interface-binding failure')
        gds=ROOT/i['gds'];top=i['top'];parent=ROOT/i['parent']
        digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
        namespace=ROOT/'build/extracted'/digest[:16]/top
        info=json.loads((namespace/'summary.json').read_text());raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist']
        if (not info['passed'] or info['returncode']!=0 or not info['ports_verified']
            or info['fingerprint']!=digest or info['gds_sha256']!=sha(gds)
            or info['source_sha256']!=sha(parent/'manifest.json') or info['source_scope_sha256']!=sha(parent/'native'/(top+'.lvs.spice'))
            or sha(raw)!=info['reduction']['source_sha256'] or sha(reduced)!=info['netlist_sha256']
            or info['ports']==bi['graph']['ports']):raise ValueError('Retained extraction has a different provenance or failure')
        text=raw.read_text();canonical,proof=ports.canonicalize(text,top,bi['graph']['ports'])
        if proof['original_ports']!=info['ports'] or not proof['header_changed']:raise ValueError('Require exactly the known public-header permutation')
        files={str(p.relative_to(ROOT)):sha(p) for p in namespace.rglob('*') if p.is_file()}
        return i,bi,info,files,proof


def prepare(failed):
    old,bi,info,files,proof=retained(failed)
    paths=[p for p in failed.rglob('*') if p.is_file()]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(old,version=VERSION,source_partial=str(failed.relative_to(ROOT)),original_info=info,original_extracted_files=files,
           public_header_proof=proof,inputs={**old['inputs'],**files,**{str(p.relative_to(ROOT)):sha(p) for p in paths}},scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or mathematics.math_proof()['runtime']!=i['math_runtime']):raise ValueError('Retained canonical bank RC context changed')
    old,bi,info,files,proof=retained(ROOT/i['source_partial'])
    if info!=i['original_info'] or files!=i['original_extracted_files'] or proof!=i['public_header_proof']:raise ValueError('Retained extraction or public-header proof changed')
    return i,bi


def run(out):
    i,bi=bound(out);parent=ROOT/i['parent'];top=i['top'];gds=ROOT/i['gds']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial measured joint RC qualification')
        (out/'state.json').write_text('{"status":"extracting","qualified_phy":false}\n')
        native=parent/'native'/(top+'.lvs.spice')
        info=i['original_info'];original_files=i['original_extracted_files']
        raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist']
        if sha(raw)!=info['reduction']['source_sha256'] or sha(reduced)!=info['netlist_sha256']:
            raise ValueError('Original extraction hashes changed')
        if reduce_netlist(raw,out/'original_regenerated.spice')!=info['reduction'] or sha(out/'original_regenerated.spice')!=info['netlist_sha256']:
            raise ValueError('Original passive reduction does not regenerate exactly')
        rows=json.loads((geometry.MEASUREMENTS/'summary.json').read_text())['rows']
        original=raw.read_text();ordinary=native.read_text()
        ordered,port_proof=ports.canonicalize(original,top,bi['graph']['ports'])
        (out/'canonical_input.spice').write_text(ordered)
        corrected,raw_proof=correction.reconstruct(ordered,top,rows,i['profile'])
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
        parameters=native_parameters(measured,top+'_flat',collapsed.read_text(),top,i['profile'])
        fine_parameters=dict(reference=fine_junctions(measured,top+'_flat',rows),joint_rc=fine_junctions(collapsed.read_text(),top,rows))
        setup=strict_setup(target/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        result=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {top}',f'{ref_path} {top}_flat',str(setup),str(target/'lvs.log')],cwd=target,capture_output=True,text=True)
        (target/'lvs_console.log').write_text(result.stdout+result.stderr)
        if not clean_match((target/'lvs.log').read_text(),result.returncode):raise ValueError('Corrected joint RC differs from actual routed native topology')
        proof=mathematics.math_proof(raw_path,netlist)
        (target/'schur_witness.json').write_text(json.dumps(proof,indent=2)+'\n')
        if proof['runtime']!=i['math_runtime'] or not proof['proof']['passed']:raise ValueError('Corrected joint RC terminal-current witness failed')
        if correction.reconstruct(ordered,top,rows,i['profile'])!=(corrected,raw_proof):raise ValueError('Actual RC junction correction does not regenerate')
        again,idempotence=correction.reconstruct(corrected,top,rows,i['profile'])
        if again!=corrected or idempotence['corrected_devices']!=0:raise ValueError('Actual RC junction correction is not byte-idempotent')
        if any(sha(ROOT/n)!=h for n,h in original_files.items()):raise ValueError('Original extraction was changed')
        bound(out)
        final=dict(info,ports=bi['graph']['ports'],canonical_public_port_order_restored=True,raw_netlist=str(raw_path.relative_to(ROOT)),netlist=str(netlist.relative_to(ROOT)),netlist_sha256=sha(netlist),reduction=reduction,junctions_reconstructed_from_native_masks=True)
        r=dict(joint_rc_passed=True,extraction=final,original_extraction=info,original_extracted_files=original_files,
               original_extraction_preserved=True,public_port_order_correction=port_proof,raw_junction_correction=raw_proof,native_reference_correction=reference_proof,
               native_parameters=parameters,all_fine_junctions=fine_parameters,native_topology_verified=True,passivity=passivity,
               original_and_corrected_reductions_regenerated=True,independent_terminal_current_witness=proof['proof'],
               capacitance_threshold_ff=.01,electrical_qualification_passed=False,qualified_phy=False,scope=i['scope'])
        r['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
