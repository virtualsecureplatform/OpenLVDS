#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Separate Xyce transient diagnostic against a completed ngspice fine31 case.

The retained v147 run rejected inline $ annotations; strip comments only in
a separate library copy, proving all circuit tokens unchanged.
No engine or model substitution in any frozen qualification campaign. A model
warning or one-case waveform agreement cannot qualify backend equivalence.
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
import probe_measured_gang_fine_v127 as golden
from spice_dispatch import lease
from xyce_raw_aliases_v148 import normalize

ROOT=golden.ROOT
sha=golden.sha
BINARY=Path('/opt/xyce/bin/Xyce')
VERSION='explicit-xyce-versus-completed-ngspice-measured-fine31-diagnostic-v151.1'
CONTEXT='xyce_measured_fine_benchmark_v151'
SCOPE='One explicit alternative-backend full-transient diagnostic, preserving the completed ngspice source; model/backend equivalence and electrical/PHY admission remain unproven'



def library_adapter(text):
    normalized='\n'.join(line.split('$',1)[0].rstrip() for line in text.splitlines())+'\n'
    before=[line.split('$',1)[0].split() for line in text.splitlines() if line.split('$',1)[0].strip()]
    after=[line.split() for line in normalized.splitlines() if line.strip()]
    if before!=after:raise ValueError('Xyce comment adapter changed circuit tokens')
    return normalized


def fixture(parent,out,i):
    text=golden.fixture(parent,i)
    if text!=(parent/'0/bench.cir').read_text():raise ValueError('Completed golden fixture cannot regenerate')
    text=text.replace(str(parent/'bank.spice'),str(out/'bank.spice'))
    text,count=re.subn(r'(?im)^\.print\s+tran\s+', '.print tran format=raw file=bench.xyce.raw ',text)
    if count!=1:raise ValueError('Require exactly one original voltage print list')
    return text.replace('OpenLVDS '+golden.VERSION+'\n','OpenLVDS '+VERSION+'\n',1)


def prepare(parent):
    i=golden.bound(parent);r=json.loads((parent/'summary.json').read_text());row=json.loads((parent/'0/summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=1,errors=0,qualified_phy=False)
        or r['rows']!=[row] or row['error'] is not None or any(sha(parent/'0'/n)!=h for n,h in row['files'].items())
        or golden.measure(parent/'0',i)!=row['result']):raise ValueError('Require unchanged completed measured native golden case')
    version=subprocess.run([str(BINARY),'-v'],capture_output=True,text=True,check=True).stdout.strip()
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',parent/'bank.spice',parent/'0/summary.json',*[parent/'0'/n for n in row['files']],*[ROOT/n for n in i['inputs']]]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),golden_identity=i,golden_result=row['result'],golden_solver_wall_seconds=row['solver_wall_seconds'],
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
        or sha(out/'0/bench.cir')!=m['deck_sha256'] or (out/'0/bench.cir').read_text()!=fixture(parent,out,i['golden_identity'])):
        raise ValueError('Explicit Xyce benchmark context changed')
    if golden.bound(parent)!=i['golden_identity']:raise ValueError('Golden native context changed')
    return i


def compare(result,golden_result,wall,golden_wall):
    return dict(edge_delay_differences_ps=[{edge:sample[edge+'_delay_ps']-base[edge+'_delay_ps'] for edge in ['rise','fall']} for sample,base in zip(result['samples'],golden_result['samples'])],
                maximum_output_slew_difference_ps=result['maximum_output_slew_ps']-golden_result['maximum_output_slew_ps'] if result['maximum_output_slew_ps'] is not None else None,
                xyce_static_screen_passed=result['static_native_screen_passed'],xyce_slew_screen_passed=result['output_slew_domain_passed'],
                recorded_ngspice_wall_seconds=golden_wall,xyce_wall_seconds=wall,recorded_wall_time_ratio_ngspice_over_xyce=golden_wall/wall,
                standardized_performance_benchmark=False,model_equivalence_proven=False,backend_qualified=False,qualified_phy=False)


def run(out):
    i=bound(out);folder=out/'0'
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial Xyce diagnostic')
        golden.zero.baseline.atomic(out/'state.json',dict(status='running_explicit_xyce_diagnostic',qualified_phy=False));result=error=wall=conversion=comparison=None;returncode=None
        try:
            with lease(ROOT,priority=2,label=CONTEXT):
                bound(out);start=time.monotonic()
                with (folder/'console.log').open('w') as log:
                    p=subprocess.run([str(BINARY),'-linsolv','KLU','-l',str(folder/'xyce.log'),str(folder/'bench.cir')],cwd=folder,stdout=log,stderr=subprocess.STDOUT)
                wall=time.monotonic()-start;returncode=p.returncode;p.check_returncode()
            conversion=normalize(folder/'bench.xyce.raw',folder/'bench.raw')
            result=golden.measure(folder,i['golden_identity']);comparison=compare(result,i['golden_result'],wall,i['golden_solver_wall_seconds'])
        except Exception as e:error=str(e)
        output='\n'.join(f.read_text(errors='replace') for f in [folder/'console.log',folder/'xyce.log'] if f.exists())
        warnings=sorted(set(re.findall(r'version ([\d.]+) which is older than the oldest version supported in Xyce \(([\d.]+)\)',re.sub(r'\s+',' ',output))))
        row=dict(inline_comments_only_removed=True,all_circuit_tokens_preserved=True,result=result,error=error,returncode=returncode,solver_wall_seconds=wall,raw_conversion=conversion,comparison=comparison,
                 model_version_substitutions=[dict(requested=a,used=b) for a,b in warnings],warning_occurrences=len(re.findall(r'warning',output,re.I)),
                 files={p.name:sha(p) for p in folder.iterdir() if p.is_file()},model_equivalence_proven=False,qualified_phy=False)
        golden.zero.baseline.atomic(folder/'summary.json',row);bound(out)
        golden.zero.baseline.atomic(out/'summary.json',dict(rows=[row],scope=SCOPE,backend_qualified=False,qualified_phy=False))
        golden.zero.baseline.atomic(out/'state.json',dict(status='complete',cases=1,errors=int(error is not None),backend_qualified=False,qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
