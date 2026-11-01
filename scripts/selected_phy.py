#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Stage and load one explicit, audited exact-RC PHY selection for diagnostics."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import stage_phy_candidate as stage
import probe_native_driver_restore as driver
import receiver_lvt_pair_experiment as receiver
from receiver_layout_reference import cached
from dll_candidate_library import audited
from spice_library import checked_netlist
from spice_scope import closure_hash
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
DRIVER='openlvds_driver_core'
RECEIVER='openlvds_receiver_core'
BLOCKS={DRIVER,RECEIVER,'openlvds_dll_analog','lvds_bias','lvds_pfd','openlvds_tx_core','openlvds_ddr_rx','openlvds_delay_line'}
PROTECTED=('lvds_bias','openlvds_dll','openlvds_delay_line','openlvds_tx_core','openlvds_ddr_rx')
CODE={NAME,'stage_phy_candidate.py','phy_candidate.py','spice_library.py','spice_scope.py',
      'receiver_layout_reference.py','qualify_dll_candidate.py','dll_candidate_library.py',
      'digital_candidate_rc.py','physical_policy.py','rx_candidate_aperture.py',
      'rx_candidate_rc.py','rx_buffered_policy.py','receiver_static_diagnosis.py'}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def pins(text,top):
    match=re.search(r'(?im)^\.subckt[ \t]+'+re.escape(top)+r'\s+[^\n]*(?:\n\+[^\n]*)*',text)
    if not match:raise ValueError('Missing selected block '+top)
    return match[0].replace('\n+',' ').split()[2:]


def overlay(base,driver_model,receiver_model):
    for top,model in [(DRIVER,driver_model),(RECEIVER,receiver_model)]:
        if pins(base,top)!=pins(model,top):raise ValueError('Selected block changes public terminal order: '+top)
    text=stage.overlay(base,driver_model,DRIVER,PROTECTED+(RECEIVER,))
    return stage.overlay(text,receiver_model,RECEIVER,PROTECTED+(DRIVER,))


def assemble(qualification,tx,rx,comparison,receiver_layout):
    arguments=locals().copy()
    if any(not p.is_relative_to(ROOT/'build/diagnostics') for p in arguments.values()):
        raise ValueError('Use isolated physical/qualification inputs')
    base,info=stage.assemble(qualification,tx,rx=rx)
    if set(info['inputs'])!=BLOCKS:raise ValueError('Base PHY does not cover all eight selected blocks')
    comparison_manifest=json.loads((comparison/'manifest.json').read_text())
    layouts={k:(ROOT/v).resolve() for k,v in comparison_manifest['identity']['layouts'].items()}
    driver_models,driver_files,driver_code=driver.physical_models(layouts)
    driver_layout=layouts['restore_64_24'];driver_info=json.loads((driver_layout/'extraction.json').read_text())
    physical=json.loads((receiver_layout/'summary.json').read_text());identity=physical['identity']
    expected=receiver.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    if identity.get('clamp_variant')!='unclamped_lvt_pair_compact' or identity.get('diagnostic_stage')!='three_passing_source_DC_pilots':
        raise ValueError('Expected the compact LVT receiver selection')
    if any(digest(ROOT/'scripts'/n)!=sha for n,sha in identity['code'].items()):
        raise ValueError('Selected receiver producer changed')
    if any(digest(ROOT/n)!=sha for n,sha in identity['source_proofs'].items()):
        raise ValueError('Selected receiver source pilot evidence changed')
    if cached(receiver_layout,identity,expected)!=physical or not physical['passed']:
        raise ValueError('Selected receiver physical evidence changed')
    receiver_info=json.loads((receiver_layout/'extraction.json').read_text());audit=audited(receiver_layout,receiver_info)
    gds=ROOT/physical['designs'][RECEIVER]['gds']
    if (digest(gds)!=receiver_info['gds_sha256'] or physical['source_sha256']!=receiver_info['source_sha256']):
        raise ValueError('Selected receiver extraction differs from its source/GDS')
    text=overlay(base,driver_models['restore_64_24'],checked_netlist(receiver_info))
    inputs=dict(info['inputs']);inputs.update({DRIVER:driver_info['netlist_sha256'],RECEIVER:receiver_info['netlist_sha256']})
    qualified=json.loads((qualification/'manifest.json').read_text())['identity']['full_models']
    active=json.loads((ROOT/'build/extracted/current.json').read_text())['designs']
    physical_active=json.loads((ROOT/'build/layout/current.json').read_text())['designs']
    exact_models={DRIVER:driver_info,RECEIVER:receiver_info,**info['digital_models']}
    exact_models['openlvds_dll_analog']=json.loads((ROOT/qualified['layout']/'extraction.json').read_text())
    for name in ['lvds_bias','openlvds_delay_line']:exact_models[name]=active[name]
    if set(exact_models)!=BLOCKS:raise ValueError('Missing exact selected model metadata')
    for name,model in exact_models.items():
        checked_netlist(model)
        if model['netlist_sha256']!=inputs[name]:raise ValueError('Selected model hash differs from assembled input '+name)
    origins={name:str(qualification.relative_to(ROOT)) for name in BLOCKS}
    origins.update({'openlvds_dll_analog':qualified['layout'],'lvds_pfd':qualified['pfd']})
    for name in ['lvds_bias','openlvds_delay_line']:origins[name]=str(Path(physical_active[name]['gds']).parent)
    origins.update({DRIVER:str(driver_layout.relative_to(ROOT)),RECEIVER:str(receiver_layout.relative_to(ROOT)),
                    'openlvds_tx_core':str(tx.relative_to(ROOT)),'openlvds_ddr_rx':str(rx.relative_to(ROOT))})
    blocks={name:dict(model_sha256=inputs[name],closure_sha256=closure_hash(text,name),artifact=origins[name]) for name in sorted(BLOCKS)}
    files=[comparison/'manifest.json',qualification/'manifest.json',qualification/'full.spice']+driver_files
    files += [receiver_layout/n for n in ['summary.json','physical_cache.json','candidate.spice','extraction.json','rc_audit.json']]
    files += [gds,ROOT/receiver_info['netlist'],ROOT/audit['report']]
    reports=dict(info['physical_reports']);reports.update({str(p.relative_to(ROOT)):digest(p) for p in files})
    code=CODE|set(driver.CODE)|set(driver_code)|set(identity['code'])
    return text,dict(inputs=inputs,digital_models=info['digital_models'],blocks=blocks,physical_reports=reports,
        scopes={name:closure_hash(text,name) for name in set(info['scopes'])|BLOCKS},
        code={n:digest(ROOT/'scripts'/n) for n in sorted(code)},
        exact_models=exact_models)


def prepare(qualification,tx,rx,comparison,receiver_layout):
    paths=dict(qualification=qualification.resolve(),tx=tx.resolve(),rx=rx.resolve(),comparison=comparison.resolve(),receiver_layout=receiver_layout.resolve())
    text,selection=assemble(**paths)
    identity=dict(schema=1,view='exact_rc',paths={k:str(v.relative_to(ROOT)) for k,v in paths.items()},selection=selection,
        requirements_sha256=digest(ROOT/'requirements.json'),library_sha256=hashlib.sha256(text.encode()).hexdigest())
    root=ROOT/'build/diagnostics/selected_phy'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=root/'full.spice'
        if path.exists() and path.read_text()!=text:raise ValueError('Selected PHY library changed')
        if not path.exists():path.write_text(text)
        capture_manifest(root/'manifest.json',dict(identity=identity,diagnostic=True,qualified=False,
            complete_phy_suite=False,approximate_transient_qualified=False))
    return root


def load(bundle,fast=False):
    if fast:raise ValueError('Selected PHY has no certified approximate view; use exact RC')
    root=Path(bundle).resolve()
    if not root.is_relative_to(ROOT/'build/diagnostics/selected_phy'):raise ValueError('Use an explicit selected PHY context')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    if (identity.get('schema')!=1 or identity.get('view')!='exact_rc' or manifest.get('diagnostic') is not True or
            manifest.get('qualified') is not False or manifest.get('complete_phy_suite') is not False or
            manifest.get('approximate_transient_qualified') is not False):
        raise ValueError('Selected PHY selection is diagnostic and exact-RC only')
    if identity['requirements_sha256']!=digest(ROOT/'requirements.json'):raise ValueError('Selected PHY requirements changed')
    if root.name!=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]:
        raise ValueError('Selected PHY identity changed')
    selection=identity['selection']
    if set(selection['blocks'])!=BLOCKS or set(selection['inputs'])!=BLOCKS:
        raise ValueError('Selected PHY block coverage changed')
    for name,sha in selection['code'].items():
        if digest(ROOT/'scripts'/name)!=sha:raise ValueError('Selected PHY producer changed')
    for name,sha in selection['physical_reports'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or digest(path)!=sha:raise ValueError('Selected PHY physical evidence changed')
    # Reconstruct through the same scientific/physical validators used by
    # staging. No simulator, geometry builder or active pointer is invoked.
    text,actual=assemble(**{k:(ROOT/v).resolve() for k,v in identity['paths'].items()})
    path=root/'full.spice'
    if actual!=selection or digest(path)!=identity['library_sha256'] or path.read_text()!=text:
        raise ValueError('Selected PHY differs from its explicit block selection')
    return text.encode(),selection['inputs'],selection['digital_models']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','check'])
    p.add_argument('artifact',type=Path);p.add_argument('--tx',type=Path);p.add_argument('--rx',type=Path)
    p.add_argument('--driver-comparison',type=Path);p.add_argument('--receiver-layout',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if any(v is None for v in [a.tx,a.rx,a.driver_comparison,a.receiver_layout]):p.error('Specify every selected physical input')
        print(prepare(a.artifact,a.tx,a.rx,a.driver_comparison,a.receiver_layout),flush=True)
    else:
        data,inputs,_=load(a.artifact);print(json.dumps(dict(passed=True,qualified=False,library_sha256=hashlib.sha256(data).hexdigest(),inputs=inputs)),flush=True)
