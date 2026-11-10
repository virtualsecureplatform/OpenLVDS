#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolated backend/tolerance matrix and common 300 MHz active-bank controls."""
import argparse,json,math,os,re,resource,subprocess,time
from pathlib import Path
import numpy as np
from native_binary_raw_v2 import validate
from xyce_raw_aliases_v148 import normalize,digest
from dcc_source_300 import model_closure
from spice_dispatch import lease
from run_native_binary_v2 import translate

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'build/diagnostics/restored_balanced_bank_v352/67d491be912b3621'
REFERENCE=ROOT/'build/diagnostics/convergence_threads_300_v1/23caa08dd7cb678f/0/bench.raw'
RUNTIME=ROOT/'build/tools/openpll-xyce-300-v1/e07a45abe62b01ea-r2'
CONTEXT=ROOT/'build/diagnostics/openpll_xyce_benchmark_300_v1'

def sha(p):return digest(Path(p))
def save(p,d):p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def library_adapter(text):
 lines=[l.split('$',1)[0].rstrip() for l in text.splitlines()]
 result='\n'.join(lines)+'\n'
 if [l.split('$',1)[0].split() for l in text.splitlines() if l.split('$',1)[0].strip()]!=[l.split() for l in result.splitlines() if l.strip()]:raise ValueError('Circuit tokens changed')
 return result

def stimulus():
 sigma=250e-12/(2*math.atanh(.8));period=1/300e6
 terms=[]
 for k in range(8):
  rise=2.1e-9+k*period;fall=rise+.6*period
  terms.append(f'.9*(tanh((time-{rise:.17g})/{sigma:.17g})-tanh((time-{fall:.17g})/{sigma:.17g}))')
 return 'BIN IN 0 V={'+ '+'.join(terms)+'}'

def prepare():
 runtime=json.loads((RUNTIME/'runtime.json').read_text())
 bank=(SOURCE/'bank.spice').read_text();model=re.search(r'(?m)^\.lib "([^"\n]+)" ss$',(SOURCE/'0/bench.cir').read_text())
 if model is None:raise ValueError('Require original SS library')
 helpers={str(ROOT/'scripts'/n):sha(ROOT/'scripts'/n) for n in ['native_binary_raw_v2.py','xyce_raw_aliases_v148.py','dcc_source_300.py','spice_dispatch.py','spice_slots.py','run_native_binary_v2.py']}
 identity=dict(version=1,script_sha256=sha(__file__),helpers=helpers,runtime_sha256=sha(RUNTIME/'runtime.json'),runtime=runtime,
  source_files={str(p):sha(p) for p in [SOURCE/'bank.spice',SOURCE/'0/bench.cir',SOURCE/'1/bench.cir',REFERENCE]},
  production_sha256=sha(ROOT/'build/tools/ngspice.json'),models=model_closure(Path(model[1])),
  reltol=1e-4,absolute_tolerances=[1e-12,1e-9],cpu=max(os.sched_getaffinity(0)),max_workers=1,priority=2,
  quiet_stop=20e-12,active_stop=30e-9,active_clock_mhz=300,active_duty=.6,active_slew_ps=250,qualified_phy=False)
 import hashlib
 out=CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
 (out/'bank.ngspice').write_text(bank);(out/'bank.xyce').write_text(library_adapter(bank));tasks=[]
 specs=[('quiet',backend,a) for a in identity['absolute_tolerances'] for backend in ('ngspice','xyce_klu','xyce_umfpack')]
 specs += [('active',backend,1e-9) for backend in ('ngspice','xyce_klu','xyce_umfpack')]
 for k,(kind,backend,abstol) in enumerate(specs):
  folder=out/str(k);folder.mkdir();text=(SOURCE/('0' if kind=='quiet' else '1')/'bench.cir').read_text()
  if kind=='active':
   text,n=re.subn(r'(?m)^BIN IN 0 V=\{[^\n]+\}$',stimulus(),text)
   if n!=1:raise ValueError('Require original smooth clock source')
  stop=20e-12 if kind=='quiet' else 30e-9
  text=text.replace('.tran 2p 25n 0 2p','.tran 2p '+('20p' if kind=='quiet' else '30n')+' 0 2p')
  text=text.replace('abstol=1e-12',f'abstol={abstol:.17g}')
  if backend=='ngspice':
   text=text.replace(str(SOURCE/'bank.spice'),str(out/'bank.ngspice'));text,names=translate(text)
   control=f'.control\nset num_threads = 1\nset filetype = binary\nrun\nwrite {folder}/bench.raw all\n.endc\n'
   text=text.replace('.end\n',control+'.end\n')
  else:
   original,names=translate(text)
   text=text.replace(str(SOURCE/'bank.spice'),str(out/'bank.xyce'))
   text=text.replace('.options device temp=40',f'.options parser model_binning=true\n.options device temp=40\n.options nonlin reltol=1e-4 abstol={abstol:.17g}')
   text=text.replace('.print tran ',f'.print tran format=raw precision=17 file={folder}/bench.xyce.raw ')
  (folder/'bench.cir').write_text(text)
  tasks.append(dict(id=str(k),kind=kind,backend=backend,abstol=abstol,stop=stop,deck_sha256=sha(folder/'bench.cir')))
 validate(REFERENCE,set(names),20e-12)
 save(out/'manifest.json',dict(identity=identity,tasks=tasks,names=['time',*names],libraries={n:sha(out/n) for n in ('bank.ngspice','bank.xyce')},qualified_phy=False));print(out,flush=True)

def crossings(t,v,up):
 ix=np.flatnonzero((v[:-1]<.9)&(v[1:]>=.9) if up else (v[:-1]>.9)&(v[1:]<=.9))
 return t[ix]+(.9-v[ix])*(t[ix+1]-t[ix])/(v[ix+1]-v[ix])

def compare(ref,path,names,stop,active):
 bn,bw=validate(ref,set(names),stop);ns,w=validate(path,set(names),stop)
 if set(bn)!=set(ns) or set(ns)!=set(names):raise ValueError('Different native vector set')
 bt=bw[:,bn.index('time')];t=w[:,ns.index('time')]
 errors={n:float(np.max(np.abs(np.interp(bt,t,w[:,ns.index(n)])-bw[:,bn.index(n)]))) for n in ns if n!='time'}
 dc={n:abs(float(w[0,ns.index(n)]-bw[0,bn.index(n)])) for n in errors}
 result=dict(maximum_voltage_error_v=max(errors.values()),worst_voltage_vector=max(errors,key=errors.get),maximum_dc_error_v=max(dc.values()),worst_dc_vector=max(dc,key=dc.get),dc_within_2mv=max(dc.values())<=.002)
 if active:
  events={};matched=True;deltas=[]
  for n in ('v(in)','v(out)'):
   for up in (True,False):
    a=crossings(bt,bw[:,bn.index(n)],up);b=crossings(t,w[:,ns.index(n)],up);same=len(a)==len(b)==8
    difference=[float(x*1e12) for x in b-a] if len(a)==len(b) else []
    events[n+('_rise' if up else '_fall')]=dict(reference_count=len(a),candidate_count=len(b),differences_ps=difference)
    matched &= same;deltas+=difference
  result.update(events=events,all_eight_edges_each_direction=bool(matched),maximum_crossing_error_ps=max(map(abs,deltas)) if deltas else None,
   timing_screen_within_10ps=bool(matched and max(map(abs,deltas))<=10))
 return result

def run(out):
 m=json.loads((out/'manifest.json').read_text());i=m['identity']
 def check():
  files={__file__:i['script_sha256'],RUNTIME/'runtime.json':i['runtime_sha256'],ROOT/'build/tools/ngspice.json':i['production_sha256'],**i['helpers'],**i['models']}
  files.update({out/n:h for n,h in m['libraries'].items()})
  for row in i['runtime']['runtimes']:files.update({row['binary']:row['sha256'],**row['libraries']})
  for n,h in json.loads((ROOT/'build/tools/ngspice.json').read_text())['files'].items():files[ROOT/n]=h
  for p,h in files.items():
   if sha(p)!=h:raise ValueError('Captured input changed: '+str(p))
 check()
 if (out/'state.json').exists():raise ValueError('Retain original run')
 save(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
 for task in m['tasks']:
  folder=out/task['id'];backend=task['backend']
  if sha(folder/'bench.cir')!=task['deck_sha256']:raise ValueError('Deck changed')
  if backend=='ngspice':
   runtime=ROOT/'build/tools/ngspice-runtime';command=[str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice'),'-n','-b','-o',str(folder/'native.log'),str(folder/'bench.cir')]
  else:
   runtime=next(r for r in i['runtime']['runtimes'] if r['label']==('stock' if backend=='xyce_klu' else 'umfpack'))
   command=[runtime['binary'],'-linsolv','KLU' if backend=='xyce_klu' else 'umfpack_reuse','-l',str(folder/'native.log'),str(folder/'bench.cir')]
  env=dict(os.environ,OMP_NUM_THREADS='1',OMP_THREAD_LIMIT='1',OPENBLAS_NUM_THREADS='1');env.pop('OPENLVDS_STEP_TRACE',None)
  def limits():
   os.sched_setaffinity(0,{i['cpu']});resource.setrlimit(resource.RLIMIT_AS,(16*1024**3,16*1024**3))
  with lease(ROOT,priority=2,label='openpll_xyce_benchmark_300_v1_'+task['id']):
   check();usage=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.monotonic()
   with (folder/'console.log').open('w') as log:p=subprocess.run(command,cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limits)
   elapsed=time.monotonic()-start;after=resource.getrusage(resource.RUSAGE_CHILDREN)
  row=dict(task=task,returncode=p.returncode,wall_seconds=elapsed,child_cpu_seconds=after.ru_utime+after.ru_stime-usage.ru_utime-usage.ru_stime,command=command,cpu=i['cpu'],complete=False,qualified_phy=False)
  output='\n'.join(f.read_text(errors='replace') for f in (folder/'console.log',folder/'native.log') if f.exists());flat=re.sub(r'\s+',' ',output)
  row.update(model_version_substitutions=re.findall(r'version ([\d.]+) which is older than the oldest version supported in Xyce \(([\d.]+)\)',flat),
   warning_occurrences=len(re.findall('warning',output,re.I)),warning_lines=[l[:500] for l in output.splitlines() if re.search('warning|ignor|unrecognized|unknown|clamp',l,re.I)][:100])
  try:
   if p.returncode:raise ValueError('Simulator returned '+str(p.returncode))
   if backend!='ngspice':row['normalization']=normalize(folder/'bench.xyce.raw',folder/'bench.raw')
   ns,w=validate(folder/'bench.raw',set(m['names']),task['stop'])
   if set(ns)!=set(m['names']):raise ValueError('Different vector set')
   row.update(complete=True,records=len(w),final_time=float(w[-1,ns.index('time')]))
   ref=REFERENCE if task['kind']=='quiet' else out/'6/bench.raw'
   row['comparison']=compare(ref,folder/'bench.raw',m['names'],task['stop'],task['kind']=='active')
   if task['kind']=='quiet' and rows and rows[0]['complete']:row['fresh_ngspice_wall_ratio']=rows[0]['wall_seconds']/elapsed
   if task['kind']=='active' and task['id']!='6' and rows[6]['complete']:row['fresh_ngspice_wall_ratio']=rows[6]['wall_seconds']/elapsed
  except Exception as exc:row['error']=str(exc)
  row['files']={f.name:sha(f) for f in folder.iterdir() if f.is_file()};save(folder/'summary.json',row);rows.append(row)
  save(out/'progress.json',dict(completed=len(rows),failed=[r['task']['id'] for r in rows if not r['complete'] or 'error' in r],qualified_phy=False))
 check();save(out/'summary.json',dict(rows=rows,scope='One SS40 exact-bank quiet solver/tolerance matrix and common 300 MHz active timing comparison; model equivalence and production adoption unproven',qualified_phy=False));save(out/'state.json',dict(status='complete',qualified_phy=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
 if a.action=='prepare':prepare()
 else:run(a.artifact.resolve())
