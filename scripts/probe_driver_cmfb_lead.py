#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One calculated CMFB lead network, tested against matched extracted devices."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import driver_source_campaign as campaign
import probe_driver_compact_native as pilot
import probe_driver_intrinsic_corners as baseline
import probe_driver_wire_loading as wire
from dll_campaign import text_block
from receiver_static_diagnosis import capture_manifest
from spice_library import replace

ROOT=Path(__file__).resolve().parents[1]
sha=wire.sha
NEW='cmfb_lead_one_direct_five_series_r0p35_l1p25'
POINTS=[('tt',25),('ss',25),('ff',40)]


def lead_block(block):
    lines=block.splitlines();selected=[]
    for i,line in enumerate(lines):
        w=line.split()
        if not w or w[0][0].lower()!='x' or 'sky130_fd_pr__cap_mim_m3_1' not in w:continue
        params=dict(v.split('=',1) for v in w if '=' in v)
        if abs(float(params['w'])-29.)<.05 and abs(float(params['l'])-29.)<.05:selected.append((i,w,params))
    if len(selected)!=6 or len({tuple(sorted(p.items())) for _,_,p in selected})!=1:
        raise ValueError('Require the original six identical 29 um CMFB MIMs')
    nodes=[]
    for _,w,_ in selected:
        if (w[1]=='VSS')==(w[2]=='VSS'):raise ValueError('Require one grounded plate per compensation MIM')
        nodes.append(w[2] if w[1]=='VSS' else w[1])
    if len(set(nodes))!=1:raise ValueError('Original compensation plates are not one node')
    output=nodes[0];node='CMFB_LEAD_C'
    if node in block or 'XCMFB_RZ0' in block:raise ValueError('Lead network already exists')
    for i,w,_ in selected[1:]:
        w[2 if w[1]=='VSS' else 1]=node;lines[i]=' '.join(w)
    index=next(i for i,l in enumerate(lines) if l.lower().startswith('.ends'))
    lines.insert(index,f'XCMFB_RZ0 {output} {node} VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=1.25')
    return '\n'.join(lines)


def transform(model,block_name):
    return replace(model,block_name,lead_block(text_block(model,block_name)))


def measure(folder):
    return pilot.measure(folder)[0]


def prepare(completed):
    m=campaign.context(completed,baseline);r=json.loads((completed/'summary.json').read_text())
    if r.get('required_cases')!=4 or r.get('required_pvt')!=2 or r.get('manifest_sha256')!=sha(completed/'manifest.json'):
        raise ValueError('Require completed SS25/FF40 intrinsic device controls')
    rows=[];paths=[completed/'manifest.json',completed/'summary.json']
    for task in m['tasks']:
        folder=completed/task['id'];row=json.loads((folder/'summary.json').read_text())
        if (row['returncode']!=0 or row['error'] is not None or row['manifest_sha256']!=sha(completed/'manifest.json') or
                any(sha(folder/n)!=h for n,h in row['files'].items()) or baseline.measure(folder)!=row['metrics'] or
                campaign.reference.shape.initial_dc(*campaign.completed_wave(folder))!=row['initial_dc']):
            raise ValueError('Completed intrinsic control output changed')
        paths += [folder/n for n in set(task['files'])|set(row['files'])|{'summary.json'}];rows.append(row)
    if campaign.aggregate(completed,m,rows)!=r or not any(p['process']=='ff' and p['passed'] is False for p in r['pvt']):
        raise ValueError('Require the independently reproduced fast-corner intrinsic failure')
    wc=ROOT/m['identity']['parent'];wm=wire.bound(wc);parent=ROOT/wm['identity']['parent'];pm=pilot.bound(parent)
    native=transform((completed/'ss_25_negative_op/source.spice').read_text(),wire.observer.assembly.TOP)
    original_source=ROOT/pm['identity']['source']/'tt_25_negative_op/source.spice'
    design=transform(original_source.read_text(),'lvds_cmfb')
    proposal=ROOT/'build/diagnostics/driver_cmfb_lead_design'/hashlib.sha256(design.encode()).hexdigest()[:16]/'source.spice'
    proposal.parent.mkdir(parents=True,exist_ok=True)
    if proposal.exists() and proposal.read_text()!=design:raise ValueError('Calculated design proposal changed')
    if not proposal.exists():proposal.write_text(design)
    inputs=dict(m['identity']['inputs']);paths += [original_source,proposal]
    tasks=campaign.tasks(POINTS)
    for task in tasks:paths += [parent/task['id']/n for n in ['bench.cir','source.spice']]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(m['identity']['code']);code['probe_driver_cmfb_lead.py']=sha(Path(__file__))
    identity=dict(parent=str(completed.relative_to(ROOT)),recipe=NEW,stage='pilot',points=[list(p) for p in POINTS],
        inputs=inputs,code=code,simulator=pilot.provenance(),design_proposal=str(proposal.relative_to(ROOT)),
        scope='One calculated compensation candidate: one original MIM remains directly '
        'at SINK, five original MIMs share a series PDK resistor w=.35/l=1.25. '
        'Total MIM geometry, every MOS and intentional original passive retained. '
        'Matched extracted-device/ideal-core-wire model, original source bias and '
        'complete 80 ns/1 ps fixtures at TT25/SS25/FF40, both polarities. '
        'Actual transistor-level design proposal is saved separately and is not '
        'the simulated wire model. This diagnostic cannot admit either proposal '
        'as physical hardware, native RC, reliability or a qualified PHY.')
    out=ROOT/'build/diagnostics/driver_source_pilot'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    for task in tasks:
        folder=out/task['id'];folder.mkdir(exist_ok=True);old=parent/task['id']
        deck=pilot.fixture((old/'bench.cir').read_text(),old,folder)
        pilot.ProbeNetwork(native).validate(deck,['D','P','N'])
        for n,body in [('source.spice',native),('bench.cir',deck)]:
            path=folder/n
            if path.exists() and path.read_text()!=body:raise ValueError('Prepared lead compensation control changed')
            if not path.exists():path.write_text(body)
        task['files']={n:sha(folder/n) for n in ['source.spice','bench.cir']}
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='run':campaign.run(a.artifact.resolve(),sys.modules[__name__])
    else:
        _,proofs=campaign.verified(a.artifact.resolve(),sys.modules[__name__]);print(json.dumps(dict(verified=True,proofs=len(proofs))),flush=True)
