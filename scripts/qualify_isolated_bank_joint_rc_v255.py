#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify fresh routed isolated-bank RC with geometry-bound fine junctions."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import build_isolated_fine_native_gds_v253 as physical
import analyze_isolated_fine_junctions_v246 as geometry
import isolated_bank_junctions_v251 as correction
import isolated_fine_bank_inventory_v244 as inventory
import extract_native_flat_v4 as extractor
import native_public_port_order_v171 as public_ports
import verify_tg_bank_joint_rc_v52 as mathematics
from verify_measured_balanced_joint_rc_v155 import fine_junctions
from audit_passive_rc_v3 import audit
from reduce_rc import reduce_netlist
from lvs_utils import strict_setup,clean_match

ROOT=physical.ROOT
sha=physical.sha
VERSION='isolated-bank-fresh-routed-rc-fine-junctions-native-lvs-schur-v255.1'
CONTEXT='isolated_bank_joint_rc_v255'
SCOPE='Fresh actual routed isolated-bank distributed RC, exact 1479-MOS/43-MIM native inventory, measured fine junctions, strict topology/parameters, passive exact reduction and independent terminal-current proof; no periodic/PVT/clock-chain/PHY admission'


def require_physical(state,r):
    p=r.get('physical') or {};n=r.get('native_parameters') or {}
    if (state!=dict(status='complete',passed=True,qualified_phy=False) or r.get('native_routed_gds_passed') is not True
        or p.get('passed') is not True or p.get('drc_count')!='0' or p.get('lvs_passed') is not True
        or n.get('native_mos')!=1479 or n.get('native_mims')!=43 or n.get('newly_characterized_junction_devices')!=155
        or any(n.get(k) is not True for k in ('native_parameters_preserved','all_native_model_dimensions_preserved','all_reference_supplied_junctions_preserved'))
        or not r.get('final_mask_proof') or not r.get('final_native_hierarchy_proof')):
        raise ValueError('Require complete routed isolated native DRC/LVS, masks and parameters')


def port_anchors(graph,plan):
    order=graph['ports']
    if len(set(order))!=len(order) or set(order)!=set(plan['ports']):raise ValueError('Native graph and physical public ports differ')
    return {n:dict(x_um=(plan['ports'][n]['rect'][0]+plan['ports'][n]['rect'][2])/2,
                   y_um=(plan['ports'][n]['rect'][1]+plan['ports'][n]['rect'][3])/2) for n in order}


def inputs(parent,evidence):
    state=json.loads((parent/'state.json').read_text());r=json.loads((parent/'summary.json').read_text());require_physical(state,r)
    pi,bank=physical.bound(parent)
    if any(sha(parent/n)!=h for n,h in r['files'].items()):raise ValueError('Routed native GDS outputs changed')
    gi,_=geometry.bound(evidence);gr=json.loads((evidence/'summary.json').read_text())
    if (json.loads((evidence/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or not gr['analysis_completed'] or gr['geometry']!=gi['geometry'] or gi['parent']!=pi['placement']
        or pi['native_reference']!=str((evidence/'reference.spice').relative_to(ROOT))
        or gr['geometry']['fine_instances']!=31 or not gr['geometry']['measured_primitive_junction_geometry_bound']
        or not gr['geometry']['all_fine_active_regions_separate_between_instances']
        or any(sha(evidence/n)!=h for n,h in gr['files'].items())):
        raise ValueError('Require exact measured fine geometry and corrected reference for this native placement')
    gds=ROOT/r['physical']['gds'];placed=ROOT/pi['placement'];top=bank['graph']['top']
    if physical.original.native_cells(gds,placed,bank)!=r['final_native_hierarchy_proof']:raise ValueError('Final routed native hierarchy/placements changed')
    if physical.original.legacy.masks(gds,placed/(top+'.gds'),top,bank['plan']['die'])!=r['final_mask_proof']:raise ValueError('Final routed native manufacturing masks changed')
    port_anchors(bank['graph'],bank['plan'])
    return pi,bank,r,gi,gr,gds


def prepare(parent,evidence):
    pi,bank,r,gi,gr,gds=inputs(parent,evidence);paths=[]
    for folder,report in ((parent,r),(evidence,gr)):
        paths += [folder/n for n in ('manifest.json','summary.json','state.json',*report['files'])]
    paths += [ROOT/n for n in {*pi['inputs'],*gi['inputs']}]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),geometry=str(evidence.relative_to(ROOT)),
        top=bank['graph']['top'],graph=bank['graph'],plan=bank['plan'],gds=str(gds.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},math_runtime=mathematics.math_proof()['runtime'],scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or mathematics.math_proof()['runtime']!=i['math_runtime']):
        raise ValueError('Isolated bank native RC context changed')
    _,bank,_,_,_,gds=inputs(ROOT/i['parent'],ROOT/i['geometry'])
    if bank['graph']!=i['graph'] or bank['plan']!=i['plan'] or str(gds.relative_to(ROOT))!=i['gds']:
        raise ValueError('Isolated native observation metadata or GDS changed')
    return i


def verify_fresh(info,digest,gds,manifest,native,ports):
    if (info.get('passed') is not True or info.get('returncode')!=0 or info.get('ports_verified') is not True
        or info.get('ports')!=ports or info.get('fingerprint')!=digest or info.get('gds_sha256')!=sha(gds)
        or info.get('source_sha256')!=sha(manifest) or info.get('source_scope_sha256')!=sha(native)):
        raise ValueError('Fresh routed isolated RC failed exact source/interface binding')


def witness_view(text):
    """Remove only legal inline comments for the unchanged math parser."""
    result='\n'.join(line.split('$',1)[0] for line in text.splitlines())+'\n'
    def tokens(value):
        return [line.split('$',1)[0].split() for line in value.splitlines()
                if line.split('$',1)[0].strip() and not line.lstrip().startswith('*')]
    if tokens(result)!=tokens(text):raise ValueError('Independent witness comment view changed circuit tokens')
    return result


def qualify_netlists(folder,original,ordinary,top,ports,rows,math_runtime):
    """Verify netlist transformation; callers must first prove routed geometry."""
    folder.mkdir();ordered,port_proof=public_ports.canonicalize(original,top,ports)
    (folder/'canonical_input.spice').write_text(ordered)
    corrected,raw_proof=correction.reconstruct(ordered,top,rows)
    measured,reference_proof=correction.reconstruct(ordinary,top+'_flat',rows)
    raw=folder/'raw.spice';ref=folder/'measured_reference.spice';reduced=folder/'reduced.spice'
    raw.write_text(corrected);ref.write_text(measured)
    if raw_proof['passive_record_count']==0:raise ValueError('Actual joint RC has no passive elements')
    passivity={label:audit(text) for label,text in [('original_raw',original),('corrected_raw',corrected)]}
    if not all(p['elementwise_passive_passed'] for p in passivity.values()):raise ValueError('Original or corrected routed RC is not passive')
    reduction=reduce_netlist(raw,reduced);passivity['corrected_reduced']=audit(reduced.read_text())
    if not passivity['corrected_reduced']['elementwise_passive_passed']:raise ValueError('Corrected reduced RC is not passive')
    if reduce_netlist(raw,folder/'regenerated.spice')!=reduction or sha(folder/'regenerated.spice')!=sha(reduced):
        raise ValueError('Corrected passive reduction does not regenerate exactly')
    collapsed=folder/'wire_collapsed.spice';collapsed.write_text(correction.collapse(reduced.read_text()))
    parameters=inventory.verify(correction.collapse(measured),top+'_flat',collapsed.read_text(),top)
    if parameters['newly_characterized_junction_devices']!=0:raise ValueError('Corrected native RC may not infer any junctions')
    fine=dict(reference=fine_junctions(measured,top+'_flat',rows),joint_rc=fine_junctions(collapsed.read_text(),top,rows))
    setup=strict_setup(folder/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
    result=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {top}',f'{ref} {top}_flat',str(setup),str(folder/'lvs.log')],cwd=folder,capture_output=True,text=True)
    (folder/'lvs_console.log').write_text(result.stdout+result.stderr)
    if not clean_match((folder/'lvs.log').read_text(),result.returncode):raise ValueError('Corrected RC differs from actual routed native topology')
    witness_raw=folder/'witness_raw.spice';witness_reduced=folder/'witness_reduced.spice'
    witness_raw.write_text(witness_view(corrected));witness_reduced.write_text(witness_view(reduced.read_text()))
    try:proof=mathematics.math_proof(witness_raw,witness_reduced)
    except subprocess.CalledProcessError as e:
        (folder/'schur_failure.log').write_text((e.stdout or '')+(e.stderr or ''))
        raise ValueError('Independent RC witness failed: '+(e.stderr or str(e))[-2000:]) from e
    (folder/'schur_witness.json').write_text(json.dumps(proof,indent=2)+'\n')
    if proof['runtime']!=math_runtime or not proof['proof']['passed']:raise ValueError('Corrected RC independent terminal-current witness failed')
    if correction.reconstruct(ordered,top,rows)!=(corrected,raw_proof):raise ValueError('Actual RC correction does not regenerate')
    again,idempotence=correction.reconstruct(corrected,top,rows)
    if again!=corrected or idempotence['corrected_devices']!=0:raise ValueError('Actual RC correction is not byte-idempotent')
    return dict(raw_junction_correction=raw_proof,native_reference_correction=reference_proof,public_port_order_correction=port_proof,
        native_parameters=parameters,all_fine_junctions=fine,passivity=passivity,reduction=reduction,independent_terminal_current_witness=proof['proof'],
        independent_witness_input=dict(inline_comments_only_removed=True,circuit_tokens_preserved=True,analysis_only=True,
            raw_sha256=sha(witness_raw),reduced_sha256=sha(witness_reduced),certified_raw_sha256=sha(raw),certified_reduced_sha256=sha(reduced)))


def run(out):
    i=bound(out);parent=ROOT/i['parent'];top=i['top'];gds=ROOT/i['gds']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial isolated bank RC')
        (out/'state.json').write_text('{"status":"extracting","qualified_phy":false}\n');error=None;r=None
        try:
            native=parent/'native'/(top+'.lvs.spice');digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
            namespace=ROOT/'build/extracted'/digest[:16]/top
            if namespace.exists():raise ValueError('Retain previous or partial isolated bank extraction')
            info=extractor.extract(top,gds,sha(parent/'manifest.json'),ports=port_anchors(i['graph'],i['plan']),source_scope=sha(native))
            (out/'original_extraction.json').write_text(json.dumps(info,indent=2)+'\n')
            verify_fresh(info,digest,gds,parent/'manifest.json',native,i['graph']['ports'])
            original_files={str(p.relative_to(ROOT)):sha(p) for p in namespace.rglob('*') if p.is_file()}
            raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist']
            if sha(raw)!=info['reduction']['source_sha256'] or sha(reduced)!=info['netlist_sha256']:raise ValueError('Original extraction hashes changed')
            if reduce_netlist(raw,out/'original_regenerated.spice')!=info['reduction'] or sha(out/'original_regenerated.spice')!=info['netlist_sha256']:
                raise ValueError('Original passive reduction does not regenerate exactly')
            rows=json.loads((geometry.MEASUREMENTS/'summary.json').read_text())['rows']
            proofs=qualify_netlists(out/'corrected',raw.read_text(),native.read_text(),top,i['graph']['ports'],rows,i['math_runtime'])
            if any(sha(ROOT/n)!=h for n,h in original_files.items()):raise ValueError('Original extraction changed')
            final=dict(info,raw_netlist=str((out/'corrected/raw.spice').relative_to(ROOT)),netlist=str((out/'corrected/reduced.spice').relative_to(ROOT)),
                netlist_sha256=sha(out/'corrected/reduced.spice'),reduction=proofs['reduction'],junctions_reconstructed_from_native_masks=True)
            r=dict(joint_rc_passed=True,isolated_bank_joint_rc_qualified=True,extraction=final,original_extraction=info,
                original_extracted_files=original_files,original_extraction_preserved=True,native_topology_verified=True,
                original_and_corrected_reductions_regenerated=True,capacitance_threshold_ff=.01,**proofs)
        except Exception as e:error=type(e).__name__+': '+str(e)
        bound(out);passed=error is None and r is not None
        r=dict(r or {},joint_rc_passed=passed,isolated_bank_joint_rc_qualified=passed,error=error,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
        r['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--geometry',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.geometry is None:p.error('--geometry required')
        out=prepare(out,a.geometry.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
