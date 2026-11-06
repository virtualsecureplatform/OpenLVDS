#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify actual 3um setter guard-pair geometry, native parameters and fresh RC."""
import argparse
from collections import Counter
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import build_counter_setter_guard3_pair_v181 as physical
import build_nand2b_guard_pair_v3 as original
import build_parallel_output_cell_v111 as proof
import native_bank_inventory_v51 as inventory

ROOT=physical.ROOT
sha=physical.sha
VERSION='native-3um-setter-pair-geometry-parameters-fresh-component-rc-v182.1'
CONTEXT='counter_setter_guard3_rc_v182'
OLD=original.NAME
NAME=physical.NAME
NAND='sky130_fd_sc_hd__nand2b_4'
TAP=physical.native.TAP
CAP='sky130_fd_pr__cap_mim_m3_1'


def parameter_change(before,after):
    expected={'sky130_fd_pr__nfet_01v8':18,'sky130_fd_pr__pfet_01v8_hvt':18,CAP:4}
    if dict(Counter(d['model'] for d in before))!=expected or dict(Counter(d['model'] for d in after))!=expected:
        raise ValueError('Require exactly the original 36 MOS and four MIMs')
    targets=[d for d in after if d['model']==CAP and set(d['nodes'])=={'Y','VGND'}]
    old_targets=[d for d in before if d['model']==CAP and set(d['nodes'])=={'Y','VGND'}]
    if len(targets)!=2 or len(old_targets)!=2:raise ValueError('Require exactly two output-to-ground guards')
    for ds,size in ((old_targets,1),(targets,3)):
        if any(set(d['params'])!={'w','l'} or any(inventory.exact_number(v)!=size for v in d['params'].values()) for d in ds):
            raise ValueError('Native output guard dimensions disagree with the intended 1-to-3um revision')
    normalized=copy.deepcopy(after)
    for d in normalized:
        if d['model']==CAP and set(d['nodes'])=={'Y','VGND'}:d['params']=dict(w='1',l='1')
    result=inventory.compare_parameters(before,normalized)
    return dict(normalized_reference_comparison=result,intentional_output_guard_dimensions_um=[3,3],output_guards_changed=2,
                all_mos_dimensions_and_junctions_preserved=True,other_mim_dimensions_preserved=True,qualified_phy=False)


def native_masks(before,after):
    db=proof.db;a=db.Layout();a.read(str(before));b=db.Layout();b.read(str(after))
    if a.dbu!=.001 or b.dbu!=a.dbu:raise ValueError('Native setter geometry scale changed')
    layers={(x.get_info(i).layer,x.get_info(i).datatype) for x in (a,b) for i in x.layer_indexes()}
    for name in (NAND,TAP):
        ac=a.cell(name);bc=b.cell(name)
        if ac is None or bc is None:raise ValueError('Missing native NAND2B or tap master')
        for layer in layers:
            def region(lib,c):
                n=lib.find_layer(*layer)
                return db.Region() if n is None else db.Region(c.begin_shapes_rec(n)).merged()
            if not (region(a,ac)^region(b,bc)).is_empty():raise ValueError('Native transistor/body-tap master masks changed')
    def placed(lib,top):
        result=Counter()
        def walk(cell,transform):
            if cell.name in (NAND,TAP):result[(cell.name,transform.to_s())]+=1;return
            for inst in cell.each_inst():
                if inst.is_regular_array():raise ValueError('Unexpected native placement array')
                walk(lib.cell(inst.cell_index),transform*inst.cplx_trans)
        root=lib.cell(top)
        if root is None:raise ValueError('Missing setter pair top')
        walk(root,db.ICplxTrans());return result
    aplaced=placed(a,OLD);bplaced=placed(b,NAME)
    if aplaced!=bplaced:raise ValueError('Native MOS/body-contact placements changed')
    return dict(native_nand2b_and_tap_master_masks_identical=True,all_native_gate_and_body_tap_placements_identical=True,
                transistor_macros=sum(n for (name,_),n in aplaced.items() if name==NAND),qualified_phy=False)


def sources(parent,baseline):
    m=physical.bound(parent);original.bound(baseline)
    rows=[]
    for folder,name in ((parent,NAME),(baseline,OLD)):
        r=json.loads((folder/'summary.json').read_text());matched=[v for v in r['rows'] if v['macro']==name]
        if (not r['passed'] or len(matched)!=1 or not matched[0]['passed'] or matched[0]['drc_count']!='0' or not matched[0]['lvs_passed']):raise ValueError('Require complete passing native pair geometry')
        cell=folder/name;row=matched[0]
        if sha(cell/(name+'.gds'))!=row['gds_sha256'] or sha(cell/(name+'.sch.spice'))!=row['lvs_source_sha256']:raise ValueError('Native setter physical source changed')
        rows.append((r,row,cell))
    return m,rows


def prepare(parent,baseline):
    m,rows=sources(parent,baseline);paths=[]
    for folder,(r,row,cell) in zip((parent,baseline),rows):
        paths += [folder/'manifest.json',folder/'summary.json',folder/'state.json',*[p for p in cell.iterdir() if p.is_file()]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),baseline=str(baseline.relative_to(ROOT)),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},external_files=m['identity']['pdk_files'],
           tools=physical.native.environment.tools(),math_runtime=proof.math_proof.math_proof()['runtime'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or physical.native.environment.tools()!=i['tools'] or proof.math_proof.math_proof()['runtime']!=i['math_runtime']):raise ValueError('Native setter-pair RC context changed')
    _,rows=sources(ROOT/i['parent'],ROOT/i['baseline']);return i,rows


def run(out):
    i,rows=bound(out);(_,row,cell),(_,old_row,old_cell)=rows
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial native setter-pair RC')
        (out/'state.json').write_text('{"status":"qualifying","qualified_phy":false}\n')
        masks=native_masks(old_cell/(OLD+'.gds'),cell/(NAME+'.gds'))
        normalize=lambda s:re.sub(r'\n[ \t]*\+[ \t]*',' ',s)
        ports,before=inventory.native_leaves(normalize((old_cell/(OLD+'.lvs.spice')).read_text()),OLD+'_flat')
        newports,after=inventory.native_leaves(normalize((cell/(NAME+'.lvs.spice')).read_text()),NAME+'_flat')
        if ports!=newports or newports!=physical.PORTS:raise ValueError('Native setter public interface order changed')
        changed=parameter_change(before,after)
        gds=cell/(NAME+'.gds');digest=hashlib.sha256(gds.read_bytes()+Path(proof.extractor.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists():raise ValueError('Retain existing native setter-pair extraction')
        anchors={n:row['ports'][n] for n in physical.PORTS}
        rc=proof.extractor.extract(NAME,gds,sha(ROOT/i['parent']/'manifest.json'),ports=anchors,source_scope=sha(cell/(NAME+'.lvs.spice')))
        if not rc['ports_verified'] or rc['ports']!=physical.PORTS:raise ValueError('Native setter RC interface mismatch')
        verification=proof.certify(out,rc,NAME,cell/(NAME+'.lvs.spice'),40)
        bound(out)
        r=dict(component_physical_rc_passed=True,native_parameter_change=changed,native_mask_comparison=masks,
               extraction=rc,rc_proof=verification,whole_clock_rc_qualified=False,counter_timing_qualified=False,qualified_phy=False,
               scope='Actual 3um output guards in native stack-guard/body-tap setter pair, original 36 MOS and other MIMs preserved, fresh component RC; no integrated timing, all-PVT or PHY admission')
        r['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        r['extracted_files']={str((ROOT/rc[k]).relative_to(ROOT)):sha(ROOT/rc[k]) for k in ('raw_netlist','netlist')}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--baseline',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.baseline is None:p.error('--baseline required')
        out=prepare(out,a.baseline.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
