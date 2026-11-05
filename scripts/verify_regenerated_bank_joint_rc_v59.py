#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract and certify regenerated-bank joint RC with native LVS and Schur proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import build_regenerated_bank_v57 as physical
import build_tg_bank_gds_v51 as native
import extract_native_flat_v4 as extractor
from audit_passive_rc_v3 import audit
from audit_rc_comments_v2 import collapse
from reduce_rc import reduce_netlist
from lvs_utils import strict_setup,clean_match

ROOT=physical.ROOT
sha=physical.sha
VERSION='regenerated-joint-rc-full-native-junctions-and-independent-schur-witness-v59.1'
CONTEXT='regenerated_bank_joint_rc_verification_v59'


def math_proof(raw=None,reduced=None):
    code='import sys,json;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/"scripts"));import exact_rc_candidate as c;result=dict(runtime=c.math_runtime());'
    args=[]
    if raw is not None:
        code+='a=c.parse(Path(sys.argv[2]).read_text());b=c.parse(Path(sys.argv[3]).read_text());assert c.static_signature(a)==c.static_signature(b);result["proof"]=c.witness(a,b);'
        args=[str(raw),str(reduced)]
    code+='print(json.dumps(result,sort_keys=True))'
    p=subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(ROOT),*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)



def extract(parent):
    pi,_=physical.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if not r['native_regenerated_gds_passed'] or any(sha(parent/n)!=h for n,h in r['files'].items()):
        raise ValueError('Require complete unchanged regenerated native physical proof')
    name=pi['graph']['top'];gds=ROOT/r['physical']['gds']
    digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
    folder=ROOT/'build/extracted'/digest[:16]/name
    if folder.exists():raise ValueError('Retain existing or partial regenerated extraction')
    ports={n:dict(x_um=(p['rect'][0]+p['rect'][2])/2,y_um=(p['rect'][1]+p['rect'][3])/2)
           for n in pi['graph']['ports'] for p in [pi['plan']['ports'][n]]}
    info=extractor.extract(name,gds,sha(parent/'manifest.json'),ports=ports,
                           source_scope=sha(parent/'native'/(name+'.sch.spice')))
    if not info['passed'] or info['ports']!=pi['graph']['ports']:raise ValueError('Regenerated joint RC extraction failed')
    physical.bound(parent);return folder


def checked(parent):
    pi,_=physical.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if not r['native_regenerated_gds_passed'] or any(sha(parent/n)!=h for n,h in r['files'].items()):raise ValueError('Native GDS evidence changed')
    gds=ROOT/r['physical']['gds'];name=pi['graph']['top']
    digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
    folder=ROOT/'build/extracted'/digest[:16]/name
    info=json.loads((folder/'summary.json').read_text())
    raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist']
    if (not info['passed'] or info['returncode']!=0 or info['fingerprint']!=digest
            or info['gds_sha256']!=sha(gds) or info['source_sha256']!=sha(parent/'manifest.json')
            or info['source_scope_sha256']!=sha(parent/'native'/(name+'.sch.spice'))
            or info['ports']!=pi['graph']['ports'] or not info['ports_verified']
            or sha(raw)!=info['reduction']['source_sha256'] or sha(reduced)!=info['netlist_sha256']
            or not audit(raw.read_text())['elementwise_passive_passed'] or not audit(reduced.read_text())['elementwise_passive_passed']):
        raise ValueError('Joint RC input, interface or passivity changed')
    return pi,info,folder


def prepare(parent):
    pi,info,folder=checked(parent)
    r=json.loads((parent/'summary.json').read_text())
    paths=[parent/'manifest.json',parent/'summary.json',*[parent/n for n in r['files']],folder/'summary.json',
           ROOT/info['raw_netlist'],ROOT/info['netlist'],Path(__file__),Path(extractor.__file__),
           ROOT/'scripts/exact_rc_candidate.py',ROOT/'scripts/reduce_rc.py',ROOT/'scripts/audit_rc_comments_v2.py',
           ROOT/'scripts/audit_rc.py',ROOT/'scripts/audit_passive_rc_v3.py',ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),extraction=info,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},math_runtime=math_proof()['runtime'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or math_proof()['runtime']!=i['math_runtime']):raise ValueError('Joint RC verification context changed')
    pi,info,_=checked(ROOT/i['parent'])
    if info!=i['extraction']:raise ValueError('Joint RC receipt changed')
    return i,pi


def run(out):
    import fcntl
    i,pi=bound(out);parent=ROOT/i['parent'];name=pi['graph']['top'];info=i['extraction']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing joint RC proof')
        (out/'state.json').write_text('{"status":"verifying","qualified_phy":false}\n')
        raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist'];regenerated=out/'regenerated.spice'
        if reduce_netlist(raw,regenerated)!=info['reduction'] or sha(regenerated)!=info['netlist_sha256']:
            raise ValueError('Exact joint RC reduction does not regenerate')
        proof=math_proof(raw,reduced)
        (out/'schur_witness.json').write_text(json.dumps(proof,indent=2)+'\n')
        if not proof['proof']['passed'] or proof['runtime']!=i['math_runtime']:raise ValueError('Independent joint RC terminal-current witness failed')
        collapsed=out/'wire_collapsed.spice';collapsed.write_text(collapse(reduced.read_text()))
        reference=parent/'native'/(name+'.lvs.spice')
        _,expected=native.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',reference.read_text()),name+'_flat')
        _,actual=native.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',collapsed.read_text()),name)
        params=native.inventory.compare_parameters(expected,actual)
        if params['native_primitives']!=1019 or params['native_model_counts'].get('sky130_fd_pr__cap_mim_m3_1')!=68:raise ValueError('Regenerated joint-RC native inventory changed')
        setup=strict_setup(out/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        p=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {name}',f'{reference} {name}_flat',str(setup),str(out/'lvs.log')],cwd=out,capture_output=True,text=True)
        (out/'lvs_console.log').write_text(p.stdout+p.stderr)
        if not clean_match((out/'lvs.log').read_text(),p.returncode):raise ValueError('Joint RC collapsed native topology changed')
        bound(out)
        report=dict(joint_rc_passed=True,extraction=info,native_parameters=params,native_topology_verified=True,
                    exact_reduction_regenerated=True,independent_terminal_current_witness=proof['proof'],
                    capacitance_threshold_ff=.01,electrical_qualification_passed=False,qualified_phy=False,
                    scope='Actual whole-bank passive RC, all native model/junction parameters, exact reduction and native LVS; fresh transient zero/timing/control and all-PVT screens still required')
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['extract','prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='extract':print(extract(out),flush=True)
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
