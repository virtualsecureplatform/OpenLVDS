#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched 2/1/2-thread localization of the complete quiet-bank bottleneck."""
import argparse,hashlib,json,os,re,subprocess,time
from collections import Counter
from pathlib import Path
import numpy as np
from probe_convergence_cause_300_v1 import ROOT,sha,save
from native_binary_raw_v2 import validate
from analyze_step_trace_v361 import analyze
from spice_dispatch import lease

PARENT=ROOT/'build/diagnostics/bank_convergence_cause_300_v1/c8567c8e71b2e6cb'
CONTEXT=ROOT/'build/diagnostics/convergence_threads_300_v1'
STOP=20e-12

def prepare():
 m=json.loads((PARENT/'manifest.json').read_text());i=m['identity']
 if json.loads((PARENT/'state.json').read_text())['status']!='complete':raise ValueError('Require completed original bank')
 binary=Path(i['binary'])
 if sha(binary)!=i['binary_sha256']:raise ValueError('Observer changed')
 names,_=validate(PARENT/'0/bench.raw',set(m['names']),200e-12)
 helpers={str(ROOT/'scripts'/n):sha(ROOT/'scripts'/n) for n in ['probe_convergence_cause_300_v1.py','native_binary_raw_v2.py','analyze_step_trace_v361.py','spice_dispatch.py','spice_slots.py']}
 identity=dict(version=1,script_sha256=sha(__file__),helpers=helpers,parent_manifest_sha256=sha(PARENT/'manifest.json'),
  reference_sha256=sha(PARENT/'0/bench.raw'),source_deck_sha256=sha(PARENT/'0/bench.cir'),binary=str(binary),binary_sha256=sha(binary),
  bank_sha256=sha(PARENT/'bank.spice'),model_inputs=i['model_inputs'],stop=STOP,threads=[2,1,2],max_workers=1,priority=2,qualified_phy=False)
 out=CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
 (out/'bank.spice').write_bytes((PARENT/'bank.spice').read_bytes())
 deck=(PARENT/'0/bench.cir').read_text().replace(str(PARENT/'bank.spice'),str(out/'bank.spice'))
 if deck.count('.tran 2p 200p 0 2p')!=1 or deck.lower().count('.end\n')!=1 or '.control' in deck.lower():raise ValueError('Unexpected source deck')
 deck=deck.replace('.tran 2p 200p 0 2p','.tran 2p 20p 0 2p')
 tasks=[]
 for k,threads in enumerate(identity['threads']):
  folder=out/str(k);folder.mkdir()
  control=f'.control\nset num_threads = {threads}\nset filetype = binary\necho OPENLVDS_NUM_THREADS $num_threads\nrun\nwrite {folder}/bench.raw all\n.endc\n'
  text=deck.replace('.end\n',control+'.end\n');(folder/'bench.cir').write_text(text)
  tasks.append(dict(id=str(k),threads=threads,deck_sha256=sha(folder/'bench.cir')))
 save(out/'manifest.json',dict(identity=identity,tasks=tasks,names=names,qualified_phy=False));print(out,flush=True)

def run(out):
 m=json.loads((out/'manifest.json').read_text());i=m['identity']
 def check():
  for p,h in {__file__:i['script_sha256'],i['binary']:i['binary_sha256'],out/'bank.spice':i['bank_sha256'],**i['helpers'],**i['model_inputs']}.items():
   if sha(p)!=h:raise ValueError('Captured input changed: '+str(p))
 check()
 if (out/'state.json').exists():raise ValueError('Retain original execution')
 save(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
 for task in m['tasks']:
  folder=out/task['id']
  if sha(folder/'bench.cir')!=task['deck_sha256']:raise ValueError('Captured deck changed')
  env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',OPENLVDS_STEP_TRACE='1')
  command=[i['binary'],'-n','-b','-o',str(folder/'ngspice.log'),str(folder/'bench.cir')]
  counts=Counter()
  with lease(ROOT,priority=2,label='convergence_threads_300_v1_'+task['id']):
   check();start=time.monotonic()
   with (folder/'console.log').open('w') as console:
    p=subprocess.Popen(command,cwd=folder,env=env,stdout=console,stderr=subprocess.STDOUT)
    save(folder/'process.json',dict(pid=p.pid,command=command))
    while p.poll() is None:
     try:counts[len(list((Path('/proc')/str(p.pid)/'task').iterdir()))]+=1
     except FileNotFoundError:pass
     time.sleep(.25)
   elapsed=time.monotonic()-start
  log=(folder/'ngspice.log').read_text(errors='replace');failure_nodes=Counter();ratios=[]
  for line in log.splitlines():
   if not line.startswith('OLVDS_CONV '):continue
   r=dict(t.split('=',1) for t in line.split()[1:])
   if float(r['t'])>0:failure_nodes[r['node']]+=1;ratios.append(float(r['ratio']))
  row=dict(task=task,returncode=p.returncode,wall_seconds=elapsed,thread_sample_histogram=dict(counts),
   frontend_threads_reported=f'OPENLVDS_NUM_THREADS {task["threads"]}' in log,
   observed_thread_count_matches=bool(counts and max(counts)==task['threads']),steps=analyze(log),
   direct_positive_failure_nodes=dict(failure_nodes),direct_failure_median_ratio=float(np.median(ratios)) if ratios else None,complete=False,qualified_phy=False)
  try:
   ns,w=validate(folder/'bench.raw',set(m['names']),STOP)
   if ns!=m['names']:raise ValueError('Vector order differs')
   row.update(complete=True,records=len(w),final_time=float(w[-1,0]))
   if rows and rows[0]['complete']:
    bn,bw=validate(out/'0/bench.raw',set(ns),STOP)
    errors=[float(np.max(np.abs(np.interp(bw[:,0],w[:,0],w[:,j])-bw[:,j]))) for j in range(1,len(ns))]
    row['parity']=dict(maximum_voltage_error_v=max(errors),maximum_dc_error_v=float(np.max(np.abs(w[0,1:]-bw[0,1:]))),
     identical_raw_values=bool(np.array_equal(w,bw)))
  except Exception as exc:row['validation_error']=str(exc)
  row['files']={f.name:sha(f) for f in folder.iterdir() if f.is_file()};save(folder/'summary.json',row);rows.append(row)
  save(out/'progress.json',dict(completed=len(rows),qualified_phy=False))
 check();save(out/'summary.json',dict(rows=rows,qualified_phy=False));save(out/'state.json',dict(status='complete',qualified_phy=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
 if a.action=='prepare':prepare()
 else:run(a.artifact.resolve())
