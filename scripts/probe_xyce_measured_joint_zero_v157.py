#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exploratory Xyce full-bank zero, independent of the live native campaign.

Uses qualified actual routed RC and the immutable native fixture. Never grants
native/backend/PHY admission or compares speed against an incomplete trace.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import probe_measured_balanced_joint_zero_v146 as golden
from benchmark_xyce_measured_fine_v151 import library_adapter
from spice_dispatch import lease
from xyce_raw_aliases_v148 import normalize

ROOT=golden.ROOT
sha=golden.sha
BINARY=Path('/opt/xyce/bin/Xyce')
VERSION='exploratory-xyce-actual-measured-joint-rc-zero-full-trace-v157.1'
CONTEXT='xyce_measured_joint_zero_v157'
SCOPE='Explicit Xyce actual routed whole-bank zero diagnostic with original full native fixture; native trace may still be live, no backend/model equivalence, native-zero admission, speed comparison or PHY qualification'



def fixture(parent,out,i):
    text=golden.fixture(parent,i)
    if text!=(parent/'0/bench.cir').read_text():raise ValueError('Immutable actual native fixture cannot regenerate')
    text=text.replace(str(parent/'bank.spice'),str(out/'bank.spice'))
    text,count=re.subn(r'(?im)^\.print\s+tran\s+', '.print tran format=raw file=bench.xyce.raw ',text)
    if count!=1:raise ValueError('Require exactly one original voltage print list')
    return text.replace('OpenLVDS '+golden.VERSION+'\n','OpenLVDS '+VERSION+'\n',1)


def prepare(parent):
    i=golden.bound(parent)
    version=subprocess.run([str(BINARY),'-v'],capture_output=True,text=True,check=True).stdout.strip()
    # Parent state/log/raw files are live and are deliberately not captured.
    # All immutable fixture, physical-proof and model inputs remain bound.
    paths=[parent/'manifest.json',parent/'bank.spice',parent/'0/bench.cir',*[ROOT/n for n in i['inputs']]]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),source_identity=i,source_pdk_files=i['pdk_files'],native_zero_admitted=False,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},xyce=dict(path=str(BINARY),sha256=sha(BINARY),version=version),
                  image_receipt_sha256=sha(ROOT/'build/apptainer/openlvds.sif.sha256'),inline_comments_only_removed=True,source_bank_sha256=sha(parent/'bank.spice'),max_workers=1,priority=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'0').mkdir();(out/'bank.spice').write_text(library_adapter((parent/'bank.spice').read_text()))
    (out/'0/bench.cir').write_text(fixture(parent,out,i))
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,bank_sha256=sha(out/'bank.spice'),deck_sha256=sha(out/'0/bench.cir'),qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];parent=ROOT/i['parent']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['max_workers']!=1 or i['priority']!=2 or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or sha(BINARY)!=i['xyce']['sha256'] or sha(ROOT/'build/apptainer/openlvds.sif.sha256')!=i['image_receipt_sha256']
        or sha(out/'bank.spice')!=m['bank_sha256'] or sha(parent/'bank.spice')!=i['source_bank_sha256'] or (out/'bank.spice').read_text()!=library_adapter((parent/'bank.spice').read_text())
        or sha(out/'0/bench.cir')!=m['deck_sha256'] or (out/'0/bench.cir').read_text()!=fixture(parent,out,i['source_identity'])):
        raise ValueError('Explicit Xyce benchmark context changed')
    if (json.loads((parent/'manifest.json').read_text())['identity']!=i['source_identity']
        or any(sha(Path(n))!=h for n,h in i['source_pdk_files'].items())
        or sha(Path(golden.CAD))!=i['source_identity']['cad']['sha256']):raise ValueError('Qualified physical/fixture source changed')
    return i


def exploratory(result):
    r=dict(result)
    return dict(r,exploratory_zero_screen_passed=r['joint_rc_zero_screen_passed'],
                joint_rc_zero_screen_passed=False,native_zero_admitted=False,
                backend_qualified=False,model_equivalence_proven=False,
                electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)


def run(out):
    i=bound(out);folder=out/'0'
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial Xyce diagnostic')
        golden.zero.baseline.atomic(out/'state.json',dict(status='running_explicit_xyce_diagnostic',qualified_phy=False));result=error=wall=conversion=None;returncode=None
        try:
            with lease(ROOT,priority=2,label=CONTEXT):
                bound(out);start=time.monotonic()
                with (folder/'console.log').open('w') as log:
                    p=subprocess.run([str(BINARY),'-linsolv','KLU','-l',str(folder/'xyce.log'),str(folder/'bench.cir')],cwd=folder,stdout=log,stderr=subprocess.STDOUT)
                wall=time.monotonic()-start;returncode=p.returncode;p.check_returncode()
            conversion=normalize(folder/'bench.xyce.raw',folder/'bench.raw')
            result=exploratory(golden.measure(folder,i['source_identity']))
        except Exception as e:error=str(e)
        output='\n'.join(f.read_text(errors='replace') for f in [folder/'console.log',folder/'xyce.log'] if f.exists())
        warnings=sorted(set(re.findall(r'version ([\d.]+) which is older than the oldest version supported in Xyce \(([\d.]+)\)',re.sub(r'\s+',' ',output))))
        row=dict(inline_comments_only_removed=True,all_circuit_tokens_preserved=True,result=result,error=error,returncode=returncode,solver_wall_seconds=wall,raw_conversion=conversion,native_zero_admitted=False,standardized_performance_benchmark=False,
                 model_version_substitutions=[dict(requested=a,used=b) for a,b in warnings],warning_occurrences=len(re.findall(r'warning',output,re.I)),
                 files={p.name:sha(p) for p in folder.iterdir() if p.is_file()},model_equivalence_proven=False,qualified_phy=False)
        golden.zero.baseline.atomic(folder/'summary.json',row);bound(out)
        golden.zero.baseline.atomic(out/'summary.json',dict(rows=[row],scope=SCOPE,native_zero_admitted=False,backend_qualified=False,qualified_phy=False))
        golden.zero.baseline.atomic(out/'state.json',dict(status='complete',cases=1,errors=int(error is not None),native_zero_admitted=False,backend_qualified=False,qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
