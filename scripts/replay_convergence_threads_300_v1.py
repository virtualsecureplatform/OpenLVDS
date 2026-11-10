#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay terminal thread controls by vector name, preserving producer reports."""
import hashlib,json
from pathlib import Path
import numpy as np
from native_binary_raw_v2 import validate
from analyze_step_trace_v361 import analyze

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'build/diagnostics/convergence_threads_300_v1/23caa08dd7cb678f'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def replay():
 inputs={}
 def bind(p,h=None):
  actual=sha(p)
  if h is not None and h!=actual:raise ValueError('Changed input: '+str(p))
  inputs[str(p)]=actual
 for n in ('manifest.json','state.json','summary.json'):bind(SOURCE/n)
 if json.loads((SOURCE/'state.json').read_text())['status']!='complete':raise ValueError('Producer not terminal')
 m=json.loads((SOURCE/'manifest.json').read_text());i=m['identity'];producer=json.loads((SOURCE/'summary.json').read_text())
 if i['threads']!=[2,1,2] or i['stop']!=20e-12 or len(producer['rows'])!=3:raise ValueError('Different experiment')
 for p,h in {ROOT/'scripts/probe_convergence_threads_300_v1.py':i['script_sha256'],i['binary']:i['binary_sha256'],SOURCE/'bank.spice':i['bank_sha256'],**i['helpers'],**i['model_inputs']}.items():bind(p,h)
 for p in (Path(__file__),ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/analyze_step_trace_v361.py'):bind(p)
 waves=[];rows=[]
 for task,stored in zip(m['tasks'],producer['rows']):
  folder=SOURCE/task['id'];bind(folder/'summary.json')
  if stored!=json.loads((folder/'summary.json').read_text()):raise ValueError('Case summary differs')
  for n,h in stored['files'].items():bind(folder/n,h)
  bind(folder/'bench.cir',task['deck_sha256'])
  names,w=validate(folder/'bench.raw',set(m['names']),20e-12)
  if set(names)!=set(m['names']):raise ValueError('Different vector set')
  if stored['returncode'] or not stored['observed_thread_count_matches'] or not stored['frontend_threads_reported']:raise ValueError('Thread request not verified')
  if stored.get('validation_error') not in (None,'Vector order differs'):raise ValueError('Unexpected producer error')
  log=(folder/'ngspice.log').read_text();events=analyze(log)
  if json.loads(json.dumps(events))!=stored['steps']:raise ValueError('Step replay differs')
  failures=[]
  for line in log.splitlines():
   if not line.startswith('OLVDS_CONV '):continue
   r=dict(t.split('=',1) for t in line.split()[1:])
   if float(r['t'])>0:failures.append(r)
  row=dict(task=task,complete_native_trace=True,records=len(w),final_time=float(w[-1,names.index('time')]),
   requested_threads=task['threads'],thread_sample_histogram=stored['thread_sample_histogram'],wall_seconds=stored['wall_seconds'],
   steps=events,direct_positive_failures=len(failures),direct_failed_nodes=sorted({r['node'] for r in failures}),
   original_reporting_error=stored.get('validation_error'))
  if waves:
   bn,bw=waves[0];bt=bw[:,bn.index('time')];t=w[:,names.index('time')]
   errors={n:float(np.max(np.abs(np.interp(bt,t,w[:,names.index(n)])-bw[:,bn.index(n)]))) for n in names if n!='time'}
   identical_time=np.array_equal(bt,t)
   row['parity']=dict(maximum_voltage_error_v=max(errors.values()),worst_vector=max(errors,key=errors.get),
    maximum_dc_error_v=max(abs(float(w[0,names.index(n)]-bw[0,bn.index(n)])) for n in errors),
    identical_time_grid=bool(identical_time),identical_all_vectors=bool(identical_time and all(np.array_equal(w[:,names.index(n)],bw[:,bn.index(n)]) for n in names)))
  waves.append((names,w));rows.append(row)
 out=ROOT/'build/reports/convergence_threads_replay_300_v1';out.mkdir(exist_ok=False)
 result=dict(inputs=inputs,rows=rows,qualified_phy=False,scope='Matched complete 20 ps thread-localization traces; original vector-order reporting errors preserved, vectors compared by name')
 (out/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(rows,indent=2));print(out,flush=True)

if __name__=='__main__':replay()
