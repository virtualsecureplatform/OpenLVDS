#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently regenerate the routed bank reference, RC reduction and flat LVS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import extract_weighted_bank_rc_v2 as extraction
from reduce_rc import reduce_netlist

ROOT=extraction.ROOT
sha=extraction.sha
atomic=extraction.atomic
VERSION='independent-routed-repaired-weighted-bank-native-rc-verification-v2.1'
CONTEXT='weighted_bank_rc_verification_v2'


def check_report(report,state):
    if (state.get('status')!='bank_rc_complete' or report.get('passed') is not True
        or report.get('rc_topology_passed') is not True or report.get('reduced_passivity_passed') is not True
        or report.get('placement_check',{}).get('passed') is not True):
        raise ValueError('Require completed whole-bank extraction, native topology and physical checks')


def checked(parent):
    m=extraction.bound(parent)
    r=json.loads((parent/'summary.json').read_text())
    check_report(r,json.loads((parent/'state.json').read_text()))
    info=r['extraction'];raw=ROOT/info['raw_netlist'];text=extraction.checked_netlist(info)
    if (json.loads((parent/'extraction.json').read_text())!=info
        or sha(raw)!=info['reduction']['source_sha256']
        or sha(ROOT/info['netlist'])!=info['reduction']['reduced_sha256']
        or not extraction.audit(raw.read_text())['elementwise_passive_passed']
        or not extraction.audit(text)['elementwise_passive_passed']):
        raise ValueError('Raw/reduced RC identity or passivity changed')
    pm=json.loads((ROOT/m['identity']['parent']/'manifest.json').read_text())['identity']
    pr=json.loads((ROOT/m['identity']['parent']/'summary.json').read_text())
    latest=json.loads((ROOT/pr['last_state']).read_text())
    name=pm['configuration']['DESIGN_NAME'];gds=Path(latest['gds']);db=Path(latest['odb'])
    checkpoint=json.loads((ROOT/pm['parent']/'manifest.json').read_text())['identity']
    if (info['gds_sha256']!=sha(gds) or info['source_sha256']!=sha(ROOT/m['identity']['parent']/'manifest.json')
        or info['source_scope_sha256']!=sha(parent/'native_reference.spice')
        or info['fingerprint']!=hashlib.sha256(gds.read_bytes()+Path(extraction.rc.__file__).read_bytes()).hexdigest()):
        raise ValueError('Whole-bank GDS/source/extractor identity changed')
    ports=[w.split('\t')[0] for w in (parent/'ports.tsv').read_text().splitlines()]
    if len(info['ports'])!=len(ports) or set(info['ports'])!=set(ports):raise ValueError('Public bank terminal coverage changed')
    return m,r,pm,checkpoint,name,db,raw


def verify(parent):
    m,r,pm,checkpoint,name,db,raw=checked(parent)
    files=[p for p in parent.iterdir() if p.is_file() and p.name!='.execution.lock']
    files += [ROOT/r['extraction'][k] for k in ['raw_netlist','netlist']]
    files += [Path(__file__),Path(extraction.__file__),Path(extraction.native.__file__),
              ROOT/'scripts/reduce_rc.py',ROOT/'scripts/audit_passive_rc_v3.py',
              ROOT/'scripts/audit_rc_comments_v2.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),tools=m['identity']['tools'],
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    atomic(out/'state.json',dict(status='verifying',qualified_phy=False))
    check=extraction.physical.parent_flow.check_db(out,db,checkpoint['spec'],pm['configuration']['MACROS'])
    if not check['passed']:raise ValueError('Independent actual final-bank power/placement/interface check failed')
    rows=[w.split('\t') for w in (out/'connections.tsv').read_text().splitlines()]
    ports=[w.split('\t')[0] for w in (out/'ports.tsv').read_text().splitlines()]
    sc=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    sources={k:Path(v['spice'][0]).read_text() for k,v in pm['configuration']['MACROS'].items()}
    reference,counts=extraction.native.reference(name,ports,rows,sc.read_text(),sources)
    if (reference!=(parent/'native_reference.spice').read_text()
        or counts!=json.loads((parent/'native_instance_counts.json').read_text())
        or len(counts)!=r['routed_instances'] or sum(counts.values())!=r['native_primitives']):
        raise ValueError('Actual final database/native primitive reference changed')
    schematic=out/'native_reference.spice';schematic.write_text(reference);atomic(out/'native_instance_counts.json',counts)
    regenerated=out/'regenerated.spice';reduction=reduce_netlist(raw,regenerated)
    if sha(regenerated)!=r['extraction']['netlist_sha256'] or reduction!=r['extraction']['reduction']:
        raise ValueError('Exact raw-to-simulator RC reduction cannot be regenerated')
    collapsed=out/'wire_collapsed.spice';collapsed.write_text(extraction.collapse(regenerated.read_text()))
    setup=extraction.strict_setup(out/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
    log=out/'lvs.log'
    p=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {name}',f'{schematic} {name}',str(setup),str(log)],
        cwd=out,capture_output=True,text=True)
    (out/'console.log').write_text(p.stdout+p.stderr)
    passed=extraction.clean_match(log.read_text() if log.exists() else '',p.returncode)
    checked(parent)
    proof=dict(rc_topology_passed=passed,raw_and_reduced_passivity_passed=True,exact_reduction_regenerated=True,
        actual_final_database_checked=True,ports=r['extraction']['ports'],routed_instances=len(counts),
        native_primitives=sum(counts.values()),netlist_sha256=sha(regenerated),native_reference_sha256=sha(schematic))
    outputs={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['manifest.json','state.json']}
    atomic(out/'summary.json',dict(proof=proof,extraction=r['extraction'],outputs=outputs,passed=passed,
        qualified_phy=False,electrical_qualification_passed=False,
        scope='Independent fresh final-ODB native expansion, exact RC reduction, raw/reduced passivity and strict flat LVS; no delay, code, PVT or PHY admission'))
    atomic(out/'state.json',dict(status='verified' if passed else 'held_native_topology_failed',qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or not r.get('outputs') or any(sha(out/n)!=h for n,h in r['outputs'].items())
        or r['passed'] is not True or json.loads((out/'state.json').read_text())['status']!='verified'):
        raise ValueError('Independent whole-bank RC receipt changed or failed')
    _,parent_report,_,_,_,_,_=checked(ROOT/i['parent'])
    expected=dict(rc_topology_passed=True,raw_and_reduced_passivity_passed=True,exact_reduction_regenerated=True,
        actual_final_database_checked=True,ports=parent_report['extraction']['ports'],
        routed_instances=parent_report['routed_instances'],native_primitives=parent_report['native_primitives'],
        netlist_sha256=sha(out/'regenerated.spice'),native_reference_sha256=sha(out/'native_reference.spice'))
    if (r['proof']!=expected or r['extraction']!=parent_report['extraction']
        or not extraction.clean_match((out/'lvs.log').read_text())
        or sha(out/'regenerated.spice')!=parent_report['extraction']['netlist_sha256']
        or (out/'native_reference.spice').read_text()!=(ROOT/i['parent']/'native_reference.spice').read_text()):
        raise ValueError('Independent whole-bank RC proof changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path)
    a=p.parse_args();print(verify(a.artifact.resolve()),flush=True)
