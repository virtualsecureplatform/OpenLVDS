#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native component-RC feasibility of branch regeneration; no new wire proof."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import regenerated_bank_v56 as circuit
import probe_nlvt_guard2_bank_v36 as source
import verify_joint_bank_zero_v54 as failed
import probe_joint_bank_zero_v53 as common

ROOT=common.ROOT
VERSION='regenerated-first-level-mux-qualified-component-rc-feasibility-v56.1'
CONTEXT='regenerated_bank_v56'
SCOPE='951-MOS/68-MIM branch-regenerated native component-RC feasibility only; new common/control/power routing not extracted; no actual joint-RC, electrical or PHY admission'


def fixture(out,i):
    return common.fixture(out,i).replace('OpenLVDS '+common.VERSION+'\n','OpenLVDS '+VERSION+'\n',1)


def prepare(parent,evidence):
    fi=failed.bound(evidence);fr=json.loads((evidence/'summary.json').read_text())['result']
    if fr['zero_code_fast_quarter_headroom_ps']>=0 or not fr['terminal_screen_passed'] or not fr['control_settling_passed']:
        raise ValueError('Require the complete timing-only routed failure')
    m=source.bound(parent);old=m['identity'];profile='both2';task=next(t for t in m['tasks'] if t['spec']['profile']==profile)
    row=json.loads((parent/task['id']/'summary.json').read_text())
    if row['error'] is not None or any(common.sha(parent/task['id']/n)!=h for n,h in row['files'].items()):
        raise ValueError('Original complete component prototype changed')
    cells=(parent/'cells_both2.spice').read_text();bank=circuit.transform(cells,(parent/'bank_both2.spice').read_text(),source.circuit.name(profile),source.circuit.MODEL)
    ports=circuit.native.definitions(bank)[circuit.NAME][0]
    devices=circuit.native.mapped_mos(cells+bank,circuit.NAME,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    counts=circuit.primitive_counts(cells+bank,circuit.NAME)
    if len(devices)!=951 or counts.get('sky130_fd_pr__cap_mim_m3_1')!=68:raise ValueError('Unexpected regenerated native inventory')
    gates=[dict(device=g['device'],gate_node=g['gate_node'],control=g['control_node'].split(':')[-1],kind='fine') for g in old['fine_control_gates'][profile]]
    gates += [dict(device=g['device'],gate_node=g['gate_node'],control=g['control_name'],kind='tg') for g in old['tg_control_gates'][profile]]
    byname={d['name']:d for d in devices}
    if len(gates)!=133 or any(byname[g['device']]['terminals'][1]!=g['gate_node'] for g in gates):raise ValueError('Programming-gate coverage changed')
    controls=[dict(node='XD:'+n,control=n) for n in common.control_targets(0,0)]
    paths=[parent/'manifest.json',parent/task['id']/'summary.json',*[parent/task['id']/n for n in row['files']],
           parent/'cells_both2.spice',parent/'bank_both2.spice',*[ROOT/n for n in old['inputs']],
           evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in fi['inputs']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    paths += [ROOT/'scripts/run_native_binary_v2.py',ROOT/'build/tools/ngspice.json']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),failure_evidence=str(evidence.relative_to(ROOT)),spec=common.spec(),
                  top=circuit.NAME,ports=ports,model=str(Path(common.os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'),
                  observations=dict(devices=devices,programming_gates=gates,controls=controls),primitive_counts=counts,
                  inputs={str(p.relative_to(ROOT)):common.sha(p) for p in paths},pdk_files=old['pdk_files'],
                  external_files=old['external_files'],simulator=common.provenance(),max_workers=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'0').mkdir()
    common.baseline.write(out/'bank.spice',cells+'\n'+bank);common.baseline.write(out/'0/bench.cir',fixture(out,identity))
    common.baseline.atomic(out/'manifest.json',dict(identity=identity,libraries={'bank.spice':common.sha(out/'bank.spice')},deck_sha256=common.sha(out/'0/bench.cir'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or common.engine()!='ngspice' or common.provenance()!=i['simulator'] or i['spec']!=common.spec()
            or len(i['observations']['devices'])!=951 or len(i['observations']['programming_gates'])!=133
            or any(common.sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(common.sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or common.sha(out/'bank.spice')!=m['libraries']['bank.spice']
            or common.sha(out/'0/bench.cir')!=m['deck_sha256'] or (out/'0/bench.cir').read_text()!=fixture(out,i)):
        raise ValueError('Regenerated component-RC candidate changed')
    return m


def measure(out,i):
    result=common.measure(out,i)
    result['component_rc_zero_screen_passed']=result.pop('joint_rc_zero_screen_passed')
    result.update(whole_bank_rc_retained=False,component_parasitics_retained=True,scope=SCOPE,
                  new_common_routing_qualified=False,architecture='Input inversion relocated to four first-level mux outputs')
    return result


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or live regenerated candidate')
        common.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False));result=error=None;wall=None
        try:
            with common.lease(ROOT,priority=0,label=CONTEXT+'_0'):
                bound(out);start=time.monotonic()
                p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(out/'0/ngspice.log'),str(out/'0/bench.cir')],capture_output=True,text=True)
                wall=time.monotonic()-start
            common.baseline.write(out/'0/console.log',p.stdout+p.stderr);p.check_returncode();result=measure(out,i)
        except Exception as e:error=str(e)
        row=dict(spec=i['spec'],result=result,error=error,solver_wall_seconds=wall,files={p.name:common.sha(p) for p in (out/'0').iterdir() if p.is_file()})
        common.baseline.atomic(out/'0/summary.json',row);bound(out)
        common.baseline.atomic(out/'summary.json',dict(rows=[row],qualified_phy=False,scope=SCOPE));common.baseline.atomic(out/'state.json',dict(status='complete',cases=1,errors=int(error is not None),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--failure-evidence',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if a.failure_evidence is None:p.error('--failure-evidence required')
        print(prepare(a.artifact.resolve(),a.failure_evidence.resolve()),flush=True)
    else:print(run(a.artifact.resolve()),flush=True)
