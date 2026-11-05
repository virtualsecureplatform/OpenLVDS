#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract fresh routed weighted-bank RC and compare every native primitive.

Require post-route physical checks first; expand actual final OpenDB cells,
including inserted diodes/fillers, through their own native schematic scopes.
Standard flow macro-blackbox LVS does not replace this strict flat proof.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signoff_weighted_bank_v2 as physical
import extract_native_flat_v4 as rc
import dcdl_bank_native_reference_v2 as native
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from lvs_utils import strict_setup,clean_match
from spice_library import checked_netlist

ROOT=physical.ROOT
sha=physical.sha
atomic=physical.atomic
VERSION='whole-routed-repaired-weighted-bank-passive-rc-native-topology-v2.1'
CONTEXT='weighted_bank_rc_v2'


def parent_files(parent):
    m=physical.bound(parent);i=m['identity']
    r=json.loads((parent/'summary.json').read_text())
    if (r.get('physical_implementation_passed') is not True
        or not physical.physical_pass(r['returncode'],r['target_step_completed'],r['placement_check'],r['metrics'])
        or not r.get('outputs')
        or any(sha(Path(n) if Path(n).is_absolute() else ROOT/n)!=h for n,h in r['outputs'].items())):
        raise ValueError('Require unchanged whole-bank physical checks and actual output views')
    folder=ROOT/r['run'];last=ROOT/r['last_state']
    if last.parent.parent!=folder or not last.parent.name.endswith('checker-lvs'):
        raise ValueError('Require actual final LVS checker state')
    latest=json.loads(last.read_text())
    expected={str(q.relative_to(ROOT)):sha(q) for q in folder.glob('*/state_out.json')}
    expected.update({str(q.relative_to(ROOT)) if q.is_relative_to(ROOT) else str(q):sha(q)
        for q in physical.referenced_files({k:v for k,v in latest.items() if k!='metrics'})})
    if r['outputs']!=expected:raise ValueError('Incomplete physical output binding')
    if any(latest['metrics'].get(k)!=0 for k in physical.ZERO_METRICS):
        raise ValueError('Reported physical metrics differ from actual final state')
    gds=Path(latest['gds']);db=Path(latest['odb']);name=i['configuration']['DESIGN_NAME']
    sources={model:Path(row['spice'][0]) for model,row in i['configuration']['MACROS'].items()}
    sc=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    files=[parent/n for n in ['manifest.json','summary.json','state.json','config.json']]
    files += [gds,db,sc,*sources.values()]
    return m,name,gds,db,sc,sources,files


def prepare(parent):
    _,_,_,_,_,_,files=parent_files(parent)
    files += [Path(__file__),Path(physical.__file__),Path(physical.parent_flow.__file__),Path(native.__file__),Path(rc.__file__)]
    files += [ROOT/'scripts'/n for n in ['audit_rc_comments_v2.py','audit_rc.py','audit_passive_rc_v3.py',
                                       'reduce_rc.py','lvs_utils.py','spice_library.py']]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),tools=physical.parent_flow.old.tool_identity(),
        inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in files})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or physical.parent_flow.old.tool_identity()!=i['tools']
        or any(sha(Path(n) if Path(n).is_absolute() else ROOT/n)!=h for n,h in i['inputs'].items())):
        raise ValueError('Weighted-bank RC context changed')
    parent_files(ROOT/i['parent']);return m


def run(out):
    m=bound(out);parent=ROOT/m['identity']['parent']
    pm,name,gds,db,sc,sources,_=parent_files(parent)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior whole-bank extraction')
        atomic(out/'state.json',dict(status='extracting',qualified_phy=False))
        try:
            pi=json.loads((ROOT/pm['identity']['parent']/'manifest.json').read_text())['identity']
            check=physical.parent_flow.check_db(out,db,pi['spec'],pm['identity']['configuration']['MACROS'])
            if not check['passed']:raise ValueError('Fresh actual final-bank interface/placement/power check failed')
            fingerprint=hashlib.sha256(gds.read_bytes()+Path(rc.__file__).read_bytes()).hexdigest()[:16]
            if (ROOT/'build/extracted'/fingerprint/name).exists():raise ValueError('Retain prior extraction namespace')
            rows=[line.split('\t') for line in (out/'connections.tsv').read_text().splitlines()]
            ports=[line.split('\t')[0] for line in (out/'ports.tsv').read_text().splitlines()]
            reference,counts=native.reference(name,ports,rows,sc.read_text(),{k:v.read_text() for k,v in sources.items()})
            schematic=out/'native_reference.spice';schematic.write_text(reference)
            atomic(out/'native_instance_counts.json',counts)
            info=rc.extract(name,gds,sha(parent/'manifest.json'),source_scope=sha(schematic))
            atomic(out/'extraction.json',info);matched=False;reduced_passive=False
            if info['passed'] and set(info['ports'])==set(ports) and len(info['ports'])==len(ports):
                text=checked_netlist(info);passivity=audit(text);atomic(out/'reduced_passivity.json',passivity)
                reduced_passive=passivity['elementwise_passive_passed']
                if reduced_passive:
                    net=out/'wire_collapsed.spice';net.write_text(collapse(text))
                    setup=strict_setup(out/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
                    report=out/'lvs.log'
                    p=subprocess.run(['netgen','-batch','lvs',f'{net} {name}',f'{schematic} {name}',str(setup),str(report)],
                        cwd=out,capture_output=True,text=True)
                    (out/'lvs_console.log').write_text(p.stdout+p.stderr)
                    matched=clean_match(report.read_text() if report.exists() else '',p.returncode)
            bound(out)
            result=dict(extraction=info,rc_topology_passed=matched,reduced_passivity_passed=reduced_passive,
                placement_check=check,native_primitives=sum(counts.values()),routed_instances=len(counts),
                passed=bool(info['passed'] and matched and reduced_passive),
                qualified_phy=False,electrical_qualification_passed=False,
                scope='Fresh passive whole-bank RC and strict fully expanded native-device DC topology; delay range, legal codes, all-PVT and full-clock/PHY qualification remain required')
            atomic(out/'summary.json',result)
            atomic(out/'state.json',dict(status='bank_rc_complete' if result['passed'] else 'held_rc_failed',qualified_phy=False))
            return result
        except Exception as exc:
            atomic(out/'state.json',dict(status='rc_exception',error=str(exc),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
