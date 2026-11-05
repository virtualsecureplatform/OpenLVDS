#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route the exact measured balanced model only after its three-point gate.

Router coverage is not native GDS/LVS/RC or electrical/PHY qualification.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import verify_balanced_routing_interface_v136 as stored

interface=stored.interface
ROOT=interface.ROOT
sha=interface.sha
VERSION='measured-balanced-bank-three-point-gated-fixed-bus-proxy-route-v135.1'
CONTEXT='measured_balanced_bank_route_v135'
BODY='''make_tracks
set_routing_layers -signal met1-met5 -clock met1-met5
set_global_routing_layer_adjustment met1-met5 0.3
global_route -guide_file @OUT@/route.guide -allow_congestion -verbose
write_db @OUT@/global.odb
detailed_route -output_drc @OUT@/route.drc
check_placement -verbose'''


def native_gate(parent):
    # The numeric interpreter is pinned separately from the CAD interpreter.
    code='''import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'scripts')
import probe_measured_gang_sparse_v131 as p
out=Path(sys.argv[1]);m=p.bound(out);i=m['identity']
if json.loads((out/'state.json').read_text())!=dict(status='complete',cases=2,consumed_fine_cases=1,errors=0,qualified_phy=False):raise ValueError('Require complete error-free measured-gang sparse campaign')
fineout=p.ROOT/i['source_fine'];fi=p.fine.bound(fineout)
if p.fine.measure(fineout/'0',fi)!=i['source_fine_result']:raise ValueError('Consumed fine31 native timing does not reproduce')
r=json.loads((out/'summary.json').read_text());rows=r['rows']
if len(rows)!=2:raise ValueError('Incomplete native three-point coverage')
paths=[out/n for n in ['manifest.json','state.json','summary.json','bank.spice']]
for task,row in zip(m['tasks'],rows):
 folder=out/task['id']
 if row['task']!=task or row['spec']!=task['spec'] or row['error'] is not None or any(p.sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Native case lineage or outputs changed')
 actual=p.fine.measure(folder,dict(i,spec=task['spec']));actual.update(scope=p.SCOPE)
 if actual!=row['result']:raise ValueError('Native measured-gang timing does not reproduce')
 paths += [folder/'summary.json',*[folder/n for n in row['files']]]
comparison=p.compare(rows,i['source_fine_result'])
if comparison!=r['comparison'] or not comparison['measured_component_sparse_feasibility_passed']:raise ValueError('Measured-gang three-point gate has not passed')
paths += [p.ROOT/n for n in i['inputs']]
paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==p.ROOT/'scripts'})
print(json.dumps(dict(profile=i['spec']['profile'],bank_sha256=p.sha(out/'bank.spice'),comparison=comparison,external_files={**i['pdk_files'],**i['external_files']},files={str(f.relative_to(p.ROOT)):p.sha(f) for f in paths}),sort_keys=True))
'''
    p=subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(parent)],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:raise ValueError('Native routing admission refused:\n'+p.stderr[-3000:])
    return json.loads(p.stdout)


def tcl(parent,out,c):
    text=interface.adapter(parent,out,c)
    text=text.replace('# No routing in the interface preflight.',BODY.replace('@OUT@',str(out)))
    text=text.replace(f'write_db {out}/restored.odb',f'write_db {out}/routed.odb\nwrite_def {out}/routed.def')
    return text


def prepare(evidence,timing):
    ei=stored.bound(evidence);r=json.loads((evidence/'summary.json').read_text())
    if (json.loads((evidence/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['stored_database_verification_passed'] or any(sha(evidence/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require complete unchanged stored-database router interface verification')
    parent=ROOT/ei['parent'];ii,pi=interface.bound(parent);placed=ROOT/ii['parent'];gate=native_gate(timing)
    candidate=interface.placement.candidate(ROOT/pi['parent'],pi['profile'])
    if gate['profile']!=pi['profile'] or hashlib.sha256(candidate['bank'].encode()).hexdigest()!=gate['bank_sha256']:
        raise ValueError('Timing gate uses a different balanced-bank component model')
    paths=[evidence/'manifest.json',evidence/'summary.json',evidence/'state.json',*[evidence/n for n in r['files']]]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),evidence=str(evidence.relative_to(ROOT)),placement=str(placed.relative_to(ROOT)),
                  timing=str(timing.relative_to(ROOT)),profile=pi['profile'],native_gate=gate['comparison'],bank_sha256=gate['bank_sha256'],contract=ii['contract'],
                  inputs={**gate['files'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},external_files=gate['external_files'],openroad=ii['openroad'],
                  numeric_python=dict(path=str(ROOT/'build/tools/exact-rc-venv/bin/python'),sha256=sha(ROOT/'build/tools/exact-rc-venv/bin/python')),
                  scope='Gated router coverage only; streamed native GDS DRC/LVS, joint RC, periodic/PVT and PHY remain unqualified')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'route.tcl').write_text(tcl(placed,out,ii['contract']));return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or any(sha(Path(t['path']))!=t['sha256'] for t in [i['openroad'],i['numeric_python']])
        or (out/'route.tcl').read_text()!=tcl(ROOT/i['placement'],out,i['contract'])):
        raise ValueError('Gated balanced route inputs changed')
    ei=stored.bound(ROOT/i['evidence']);ii,pi=interface.bound(ROOT/ei['parent']);return i,ii,pi


def check(out,i,ii):
    parent=ROOT/i['parent']
    for kind in ['connections','ports','boxes','masters','buses']:
        if interface.rows(out,'after_'+kind+'.tsv')!=interface.rows(parent,'after_'+kind+'.tsv'):
            raise ValueError('Router changed native '+kind)
    nets={w[0]:w[1:] for w in interface.rows(out,'after_nets.tsv')}
    before={w[0]:w[1:] for w in interface.rows(parent,'after_nets.tsv')}
    if set(nets)!=set(before):raise ValueError('Router added or lost a native net')
    for name,record in nets.items():
        if record[:2]!=before[name][:2] or record[3]!=before[name][3]:raise ValueError('Router changed native supply/special/fixed-bus status')
        if name in ii['contract']['regular_wire_nets'] and record[2]!='1':raise ValueError('Missing regular route: '+name)
    return dict(all_native_connections_and_placements_preserved=True,all_public_and_master_pin_geometry_and_types_preserved=True,
                all_fixed_bus_geometry_restored=True,regular_wire_nets=len(ii['contract']['regular_wire_nets']),
                all_required_nets_have_regular_wire=True,physical_connectivity_requires_native_lvs=True)


def run(out):
    i,ii,_=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial gated routing campaign')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n')
        with (out/'openroad.log').open('w') as log:
            p=subprocess.run([i['openroad']['path'],'-no_init','-exit',str(out/'route.tcl')],cwd=out,stdout=log,stderr=subprocess.STDOUT)
        result=None;error=None
        if p.returncode==0:
            try:result=check(out,i,ii)
            except ValueError as e:error=str(e)
        violations=re.findall(r'Number of violations\s*=\s*(\d+)',(out/'openroad.log').read_text());final=int(violations[-1]) if violations else None
        passed=p.returncode==0 and result is not None and final==0;bound(out)
        r=dict(returncode=p.returncode,router_final_violations=final,connection_and_coverage_check=result,error=error,route_bringup_passed=passed,
               whole_bank_gds_drc_passed=False,whole_bank_native_lvs_passed=False,joint_rc_extracted=False,electrical_qualification_passed=False,qualified_phy=False)
        r['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--timing',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:
        if a.timing is None:p.error('--timing is required for routing admission')
        out=prepare(out,a.timing.resolve());print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
