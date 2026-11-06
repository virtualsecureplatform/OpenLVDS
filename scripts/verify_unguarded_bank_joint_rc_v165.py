#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh joint RC for the output-only 1453-MOS/40-MIM bank revision."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import build_unguarded_bank_gds_v164 as physical
import analyze_measured_bank_fine_junctions_v140 as geometry
import unguarded_bank_junctions_v165 as correction
import unguarded_bank_inventory_v165 as inventory
import extract_native_flat_v4 as extractor
import verify_tg_bank_joint_rc_v52 as mathematics
from verify_measured_balanced_joint_rc_v155 import fine_junctions
from audit_passive_rc_v3 import audit
from reduce_rc import reduce_netlist
from lvs_utils import strict_setup,clean_match

ROOT=physical.ROOT
sha=physical.sha
VERSION='unguarded-b2-fresh-whole-bank-rc-junctions-native-lvs-schur-v165.1'
CONTEXT='unguarded_bank_joint_rc_v165'
SCOPE='Fresh actual unguarded output-only b2 whole-bank RC, original native MOS and routing masks, exact 1453-MOS/40-MIM census, 155 geometry-bound fine MOS junctions, native topology/parameters, passivity, exact reduction and independent current witness; no transient/PVT/PHY admission'


def inputs(parent,evidence):
    pi,_,_=physical.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['native_routed_gds_passed'] or not r['physical']['passed']
        or r['physical']['drc_count']!='0' or not r['physical']['lvs_passed']
        or r['native_revision_proof']['native_mos']!=1453 or r['native_revision_proof']['native_mims']!=40
        or not r['final_mask_proof']['all_original_cell_masks_identical']
        or not r['final_mask_proof']['all_original_placements_identical_except_final_output_model']
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require complete unchanged native output-only bank proof')
    gi,_=geometry.bound(evidence);gr=json.loads((evidence/'summary.json').read_text())
    stock=json.loads((ROOT/pi['parent']/'manifest.json').read_text())['identity']
    if (json.loads((evidence/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or not gr['analysis_completed'] or gr['geometry']!=gi['geometry']
        or gi['parent']!=stock['placement'] or gi['profile']!='b2'
        or gr['geometry']['fine_instances']!=31 or not gr['geometry']['measured_primitive_junction_geometry_bound']
        or any(sha(evidence/n)!=h for n,h in gr['files'].items())):
        raise ValueError('Require measured geometry of the unchanged fine cells and placements')
    gds=ROOT/r['physical']['gds']
    physical.variant.mask_check(ROOT/json.loads((ROOT/pi['parent']/'summary.json').read_text())['physical']['gds'],gds,pi['position'])
    return pi,r,gi,gr,gds


def prepare(parent,evidence):
    pi,r,gi,gr,gds=inputs(parent,evidence);paths=[]
    for folder,report in ((parent,r),(evidence,gr)):
        paths += [folder/'manifest.json',folder/'summary.json',folder/'state.json',*[folder/n for n in report['files']]]
    paths += [ROOT/n for n in {**pi['inputs'],**gi['inputs']}]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),geometry=str(evidence.relative_to(ROOT)),profile='b2',
           top=pi['graph']['top'],graph=inventory.metadata(pi)['graph'],plan=inventory.metadata(pi)['plan'],gds=str(gds.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
           math_runtime=mathematics.math_proof()['runtime'],scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or mathematics.math_proof()['runtime']!=i['math_runtime']):raise ValueError('Unguarded bank RC context changed')
    pi,_,_,_,gds=inputs(ROOT/i['parent'],ROOT/i['geometry'])
    if pi['graph']['top']!=i['top'] or str(gds.relative_to(ROOT))!=i['gds'] or i['profile']!='b2':raise ValueError('Bank geometry identity changed')
    bank=inventory.metadata(pi)
    if bank['graph']!=i['graph'] or bank['plan']!=i['plan']:raise ValueError('Revised native observation metadata changed')
    return i,bank


def native_parameters(reference,reference_top,extracted,extracted_top,profile):
    return inventory.verify(correction.collapse(reference),reference_top,correction.collapse(extracted),extracted_top,profile)


def run(out):
    i,bi=bound(out);parent=ROOT/i['parent'];top=i['top'];gds=ROOT/i['gds']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial measured joint RC qualification')
        (out/'state.json').write_text('{"status":"extracting","qualified_phy":false}\n')
        native=parent/'native'/(top+'.lvs.spice')
        digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
        namespace=ROOT/'build/extracted'/digest[:16]/top
        if namespace.exists():raise ValueError('Retain previous or partial unguarded bank extraction')
        ports={n:dict(x_um=(p['rect'][0]+p['rect'][2])/2,y_um=(p['rect'][1]+p['rect'][3])/2) for n,p in bi['plan']['ports'].items()}
        info=extractor.extract(top,gds,sha(parent/'manifest.json'),ports=ports,source_scope=sha(native))
        if (not info['passed'] or not info['ports_verified'] or info['ports']!=bi['graph']['ports']
            or info['fingerprint']!=digest or info['gds_sha256']!=sha(gds)
            or info['source_sha256']!=sha(parent/'manifest.json') or info['source_scope_sha256']!=sha(native)):
            raise ValueError('Fresh unguarded whole-bank extraction failed source/interface binding')
        (out/'original_extraction.json').write_text(json.dumps(info,indent=2)+'\n')
        original_files={str(p.relative_to(ROOT)):sha(p) for p in namespace.rglob('*') if p.is_file()}
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
        parameters=native_parameters(measured,top+'_flat',collapsed.read_text(),top,i['profile'])
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--geometry',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.geometry is None:p.error('--geometry required')
        out=prepare(out,a.geometry.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
