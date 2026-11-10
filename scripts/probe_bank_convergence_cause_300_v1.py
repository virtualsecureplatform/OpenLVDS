#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Direct convergence observations on the retained complete quiet-bank fixture."""
import argparse,json,os,re,subprocess,time
from pathlib import Path
import numpy as np
from probe_convergence_cause_300_v1 import ROOT,sha,save,analyze_log
from native_binary_raw_v2 import validate
from dcc_source_300 import model_closure
from spice_dispatch import lease

SOURCE=ROOT/'build/reports/step_observer_prefix_diagnostic/20261107T130431Z/off'
OBSERVER=ROOT/'build/tools/convergence-observer-300-v1/1afd9c670a5c8f42/observer'
CONTEXT=ROOT/'build/diagnostics/bank_convergence_cause_300_v1'

def prepare():
 binary=OBSERVER/'objects/src/ngspice'
 proof=json.loads((OBSERVER/'proof.json').read_text())
 if not proof['original_convergence_exactly_recoverable'] or proof['mos_models_changed'] or proof['diode_sha256']!=proof['diode_original_sha256']:
  raise ValueError('Require observation-only simulator')
 # The parent make must have finished before this separate experiment is captured.
 if not (OBSERVER/'build.log').read_text().rstrip().endswith("/observer/objects'"):
  raise ValueError('Observer build not finished')
 text=(SOURCE/'bench.ngspice.cir').read_text()
 include=re.findall(r'(?m)^\.include "([^"\n]+)"$',text)
 if len(include)!=1:raise ValueError('Require one captured circuit include')
 bank=Path(include[0]);banktext=bank.read_text()
 if re.search(r'(?im)^\s*\.(?:inc|include|lib)\b',banktext):raise ValueError('Nested circuit includes require explicit capture')
 model=re.search(r'(?m)^\.lib "([^"\n]+)" ss$',text)
 if model is None or '.tran 2p 200p 0 2p' not in text:raise ValueError('Captured quiet fixture changed')
 names,w=validate(SOURCE/'bench.raw',{'v(vdd)','v(out)'},200e-12)
 identity=dict(version=1,script_sha256=sha(__file__),parser_sha256=sha(Path(__file__).with_name('probe_convergence_cause_300_v1.py')),
  binary=str(binary),binary_sha256=sha(binary),proof_sha256=sha(OBSERVER/'proof.json'),
  source_deck_sha256=sha(SOURCE/'bench.ngspice.cir'),source_raw_sha256=sha(SOURCE/'bench.raw'),
  bank_sha256=sha(bank),model_inputs=model_closure(Path(model[1])),production_sha256=sha(ROOT/'build/tools/ngspice.json'))
 import hashlib
 out=CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
 out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_text(banktext)
 text=text.replace(str(bank),str(out/'bank.spice'))
 tasks=[]
 for k,(variant,trace) in enumerate([('production',False),('observer',False),('observer',True)]):
  folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(text)
  tasks.append(dict(id=str(k),variant=variant,trace=trace,deck_sha256=sha(folder/'bench.cir')))
 save(out/'manifest.json',dict(identity=identity,tasks=tasks,names=names,qualified_phy=False))
 print(out,flush=True)

def run(out):
 m=json.loads((out/'manifest.json').read_text());i=m['identity']
 def check():
  files={__file__:i['script_sha256'],Path(__file__).with_name('probe_convergence_cause_300_v1.py'):i['parser_sha256'],
   i['binary']:i['binary_sha256'],OBSERVER/'proof.json':i['proof_sha256'],out/'bank.spice':i['bank_sha256'],
   ROOT/'build/tools/ngspice.json':i['production_sha256'],**i['model_inputs']}
  for p,h in files.items():
   if sha(p)!=h:raise ValueError('Captured input changed: '+str(p))
 check()
 if (out/'state.json').exists():raise ValueError('Retain previous execution')
 save(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
 for task in m['tasks']:
  folder=out/task['id']
  if sha(folder/'bench.cir')!=task['deck_sha256']:raise ValueError('Captured deck changed')
  if task['variant']=='production':
   runtime=ROOT/'build/tools/ngspice-runtime'
   command=[str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice')]
   for name,h in json.loads((ROOT/'build/tools/ngspice.json').read_text())['files'].items():
    if sha(ROOT/name)!=h:raise ValueError('Production runtime changed')
  else:command=[i['binary']]
  env=dict(os.environ,OMP_NUM_THREADS='1');env.pop('OPENLVDS_STEP_TRACE',None)
  if task['trace']:env['OPENLVDS_STEP_TRACE']='1'
  command+=['-n','-b','-r',str(folder/'bench.raw'),'-o',str(folder/'ngspice.log'),str(folder/'bench.cir')]
  with lease(ROOT,priority=2,label='bank_convergence_cause_300_v1_'+task['id']):
   check();start=time.monotonic();p=subprocess.run(command,cwd=folder,env=env,capture_output=True,text=True);elapsed=time.monotonic()-start
  (folder/'console.log').write_text(p.stdout+p.stderr)
  log=(folder/'ngspice.log').read_text(errors='replace')
  row=dict(task=task,returncode=p.returncode,wall_seconds=elapsed,analysis=analyze_log(log),complete=False,qualified_phy=False)
  try:
   names,w=validate(folder/'bench.raw',set(m['names']),200e-12)
   if set(names)!=set(m['names']):raise ValueError('Native vector set differs')
   row.update(complete=True,records=len(w),final_time=float(w[-1,0]))
   if task['id']!='0' and rows[0]['complete']:
    bn,bw=validate(out/'0/bench.raw',set(names),200e-12)
    errors={n:float(np.max(np.abs(np.interp(bw[:,0],w[:,0],w[:,names.index(n)])-bw[:,bn.index(n)]))) for n in names if n!='time'}
    row['parity']=dict(maximum_voltage_error_v=max(errors.values()),worst_vector=max(errors,key=errors.get),
     maximum_dc_error_v=max(abs(float(w[0,names.index(n)]-bw[0,bn.index(n)])) for n in errors),
     identical_time_grid=bool(np.array_equal(w[:,0],bw[:,0])))
  except Exception as exc:row['validation_error']=str(exc)
  row['files']={p.name:sha(p) for p in folder.iterdir() if p.is_file()}
  save(folder/'summary.json',row);rows.append(row);save(out/'progress.json',dict(completed=len(rows),qualified_phy=False))
 check();save(out/'summary.json',dict(rows=rows,qualified_phy=False,root_cause_proven=False))
 save(out/'state.json',dict(status='complete',qualified_phy=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
 if a.action=='prepare':prepare()
 else:run(a.artifact.resolve())
