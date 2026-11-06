#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reread native databases and reject faults, including forced FIRM-cell movement.

v133 is retained: OpenDB refused its FIRM movement before a corrupt DB existed.
Here only the injected copy is unlocked, moved, and relocked before checking.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import prepare_isolated_fine_routing_interface_v240 as interface

ROOT=interface.ROOT
sha=interface.sha
VERSION='isolated-fine-router-interface-stored-db-and-native-negative-controls-v241.1'
CONTEXT='isolated_fine_routing_interface_verification_v241'
KINDS=['connections','ports','boxes','masters','nets','buses']


def prepare(parent):
    i,pi=interface.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['interface_preflight_passed'] or r['result']!=interface.verify(parent,i,pi)
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged passing native interface preflight')
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',*[parent/n for n in r['files']]]
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profile=i['profile'],inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  openroad=i['openroad'],scope='Stored native database roundtrip and injected native faults; no routing or timing admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or sha(Path(i['openroad']['path']))!=i['openroad']['sha256']):raise ValueError('Stored router-interface verification changed')
    interface.bound(ROOT/i['parent']);return i


def snapshot(out,i,db,mutation=''):
    out.mkdir()
    template=interface.TEMPLATE.read_text();procedure=template[template.index('proc snapshot {'):template.index('snapshot {@OUT@/before}')]
    code=f'read_db {{{db}}}\nset db [ord::get_db]\nset block [ord::get_db_block]\n'+procedure+'\n'+mutation+f'\nsnapshot {{{out/"stored"}}}\n'
    if mutation:code+=f'write_db {{{out/"corrupted.odb"}}}\n'
    code+='exit\n';(out/'inspect.tcl').write_text(code)
    with (out/'openroad.log').open('w') as log:
        subprocess.run([i['openroad']['path'],'-no_init','-exit',str(out/'inspect.tcl')],cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)


def differences(observed,expected,prefix):
    return [kind for kind in KINDS if interface.rows(observed,'stored_'+kind+'.tsv')!=interface.rows(expected,prefix+'_'+kind+'.tsv')]


def run(out):
    i=bound(out);parent=ROOT/i['parent'];pi=json.loads((parent/'manifest.json').read_text())['identity'];placed=ROOT/pi['parent']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial stored database verification')
        (out/'state.json').write_text('{"status":"checking","qualified_phy":false}\n')
        positives=[]
        for name,db,prefix in [('placed',placed/'placed.odb','before'),('router_input',parent/'router_input.odb','adapted'),('restored',parent/'restored.odb','after')]:
            folder=out/name;snapshot(folder,i,db);changed=differences(folder,parent,prefix)
            if changed:raise ValueError('Stored native database differs from snapshots: '+name+' '+str(changed))
            positives.append(dict(database=name,all_six_native_snapshots_match=True))
        faults=[('missing_m4_driver_output','router_input','adapted','[[$block findInst u_fine_isolate] findITerm Y] disconnect'),
                ('m4_driver_bypasses_isolation','router_input','adapted','[[$block findInst u_fine_isolate] findITerm A] connect [$block findNet fine_node]'),
                ('missing_root_output','router_input','adapted','[[$block findInst u_switch1_0_0] findITerm Z] disconnect'),
                ('proxy_metal_shift','router_input','adapted','set term [$block findBTerm __fixed_bus_fine_node]\nset pin [lindex [$term getBPins] 0]\nset b [lindex [$pin getBoxes] 0]\nset layer [$b getTechLayer]\nset coords [list [expr {[$b xMin]+1000}] [$b yMin] [expr {[$b xMax]+1000}] [$b yMax]]\nodb::dbBox_destroy $b\nodb::dbBox_create $pin $layer {*}$coords'),
                ('lost_native_supply_type','restored','after','[$block findNet VPWR] setSigType SIGNAL'),
                ('moved_native_instance','restored','after','set inst [$block findInst u_group_compound0]\nset b [$inst getBBox]\nset x [$b xMin]\nset y [$b yMin]\n$inst setPlacementStatus PLACED\n$inst setLocation [expr {$x+1000}] $y\n$inst setPlacementStatus FIRM')]
        negatives=[]
        for name,db,prefix,mutation in faults:
            folder=out/name;snapshot(folder,i,parent/(db+'.odb'),mutation);changed=differences(folder,parent,prefix)
            if not changed:raise ValueError('Corrupted native database accepted: '+name)
            negatives.append(dict(fault=name,rejected=True,differing_native_records=changed))
        bound(out)
        r=dict(stored_database_verification_passed=True,positive_controls=positives,negative_controls=negatives,routed=False,joint_rc_extracted=False,electrical_qualification_passed=False,qualified_phy=False)
        r['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
