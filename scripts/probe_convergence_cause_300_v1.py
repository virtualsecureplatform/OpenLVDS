#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Controlled decoder and diode experiments; no PHY or backend admission."""
import argparse,hashlib,json,os,re,subprocess,time
from pathlib import Path
import numpy as np
import setup_convergence_observer_300_v1 as setup
import run_native_binary_v2 as native
from native_binary_raw_v2 import validate
from spice_dispatch import lease
from dcc_source_300 import model_closure
ROOT=setup.ROOT
SOURCE=ROOT/'build/diagnostics/decoder_dc_solver_pilot_300_v1/a8f1fd4d723330a0'
CONTEXT=ROOT/'build/diagnostics/convergence_cause_300_v1'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):
 q=p.with_suffix('.tmp');q.write_text(json.dumps(d,indent=2)+'\n');q.replace(p)
def prepare(build):
 b=json.loads((build/'summary.json').read_text())
 for r in b['builds']:
  if sha(ROOT/r['binary'])!=r['sha256']:raise ValueError('Diagnostic binary changed')
 source_deck=(SOURCE/'0/bench.cir').read_text()
 model=re.search(r'(?m)^\.lib \"([^\"\n]+)\" ss$',source_deck)
 if model is None:raise ValueError('Require original SS model library')
 identity=dict(version=1,model_inputs=model_closure(Path(model[1])),build=str(build),build_sha256=sha(build/'summary.json'),
  source=str(SOURCE),source_manifest_sha256=sha(SOURCE/'manifest.json'),
  cells_sha256=sha(SOURCE/'cells.spice'),deck_sha256=sha(SOURCE/'0/bench.cir'),
  script_sha256=sha(__file__),production_sha256=sha(ROOT/'build/tools/ngspice.json'),qualified_phy=False)
 out=CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
 out.mkdir(parents=True,exist_ok=False)
 (out/'cells.spice').write_bytes((SOURCE/'cells.spice').read_bytes())
 deck=(SOURCE/'0/bench.cir').read_text().replace(str(SOURCE/'cells.spice'),str(out/'cells.spice'))
 deck=deck.replace('.tran .1p 2p 0 .1p','.tran 2p 200p 0 2p')
 tasks=[]
 for variant,trace in [('production',False),('observer',False),('observer',True),('diode_patch',True)]:
  tasks.append(dict(kind='decoder',variant=variant,trace=trace,stop=200e-12,deck=deck))
 diode='''Diode sidewall continuation diagnostic
.model DSW D IS=1e-14 N=1 RS=0 CJ=1p M=.44 VJ=.729
+ CJSW=.25p MJSW=.2 PHP=.2 FC=.5 FCS=.5 TNOM=27
VDRV drive 0 PWL(0 0 1n 0 2n -.5 3n -.5 4n 0 5n 0)
RDRV drive node 50
DTEST 0 node DSW AREA=1 PJ=1
.temp 27
.options klu method=gear reltol=1e-8 abstol=1e-14
.save v(node)
.tran 1p 5n 0 1p
.end
'''
 for variant in ('observer','diode_patch'):
  tasks.append(dict(kind='diode',variant=variant,trace=False,stop=5e-9,deck=diode))
 for k,t in enumerate(tasks):
  folder=out/str(k);folder.mkdir();text=t.pop('deck')
  if t['kind']=='decoder':text=native.translate(text)[0]
  (folder/'bench.cir').write_text(text);t.update(id=str(k),deck_sha256=sha(folder/'bench.cir'))
 save(out/'manifest.json',dict(identity=identity,tasks=tasks,builds=b['builds'],qualified_phy=False))
 print(out,flush=True);return out

def analyze_log(text):
 counts={k:len(re.findall('kind='+k+r'\b',text)) for k in ('ni_limit','noncon_reject','trunc_decision','charge_trunc')}
 worst={};n=0
 for line in text.splitlines():
  if not line.startswith('OLVDS_CONV '):continue
  r=dict(x.split('=',1) for x in line.split()[1:]);n+=1
  ratio=float(r['ratio']);key=r['node'];old=worst.get(key)
  if old is None or ratio>float(old['ratio']):worst[key]=r
 return dict(counts=counts,convergence_failures_logged=n,worst_by_node=worst,
  logging_cap_possible=sum(counts.values())>=50000 or n>=50000)

def run(out):
 m=json.loads((out/'manifest.json').read_text());i=m['identity']
 if sha(__file__)!=i['script_sha256'] or sha(Path(i['build'])/'summary.json')!=i['build_sha256']:raise ValueError('Captured experiment changed')
 if any(sha(Path(n))!=h for n,h in i['model_inputs'].items()):raise ValueError('PDK model closure changed')
 if sha(out/'cells.spice')!=i['cells_sha256']:raise ValueError('Captured native cells changed')
 if (out/'state.json').exists():raise ValueError('Retain original experiment')
 save(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
 for t in m['tasks']:
  folder=out/t['id'];binary=None
  if sha(folder/'bench.cir')!=t['deck_sha256']:raise ValueError('Deck changed')
  if t['variant']=='production':
   runtime=ROOT/'build/tools/ngspice-runtime'
   command=[str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice')]
   descriptor=json.loads((ROOT/'build/tools/ngspice.json').read_text())
   for name,h in descriptor['files'].items():
    if sha(ROOT/name)!=h:raise ValueError('Production runtime changed')
  else:
   b=next(r for r in m['builds'] if r['variant']==t['variant']);binary=ROOT/b['binary']
   if sha(binary)!=b['sha256']:raise ValueError('Diagnostic binary changed')
   command=[str(binary)]
  env=dict(os.environ,OMP_NUM_THREADS='1');env.pop('OPENLVDS_STEP_TRACE',None)
  if t['trace']:env['OPENLVDS_STEP_TRACE']='1'
  command+=['-n','-b','-r',str(folder/'bench.raw'),'-o',str(folder/'ngspice.log'),str(folder/'bench.cir')]
  with lease(ROOT,priority=2,label='convergence_cause_300_v1_'+t['id']):
   start=time.monotonic();p=subprocess.run(command,cwd=folder,env=env,capture_output=True,text=True);elapsed=time.monotonic()-start
  (folder/'console.log').write_text(p.stdout+p.stderr)
  log=(folder/'ngspice.log').read_text(errors='replace');row=dict(task=t,returncode=p.returncode,wall_seconds=elapsed,analysis=analyze_log(log),complete=False,qualified_phy=False)
  try:
   names,w=validate(folder/'bench.raw',{'v(node)'} if t['kind']=='diode' else {'v(a)','v(b)','v(x)','v(y)','v(vdd)'},t['stop'])
   row.update(complete=True,records=len(w),final_time=float(w[-1,0]),dc={n:float(w[0,k]) for k,n in enumerate(names) if n!='time'})
   if t['kind']=='decoder' and rows[0]['complete'] and t['id']!='0':
    base=out/'0/bench.raw';bn,bw=validate(base,set(names[1:]),200e-12)
    errors={n:float(np.max(np.abs(np.interp(bw[:,0],w[:,0],w[:,names.index(n)])-bw[:,bn.index(n)]))) for n in names if n!='time'}
    row['parity']=dict(maximum_voltage_error_v=max(errors.values()),worst_vector=max(errors,key=errors.get),maximum_dc_error_v=max(abs(row['dc'][n]-rows[0]['dc'][n]) for n in row['dc']))
  except Exception as exc:row['validation_error']=str(exc)
  row['files']={p.name:sha(p) for p in folder.iterdir() if p.is_file()}
  save(folder/'summary.json',row);rows.append(row)
  save(out/'progress.json',dict(completed=len(rows),qualified_phy=False))
 save(out/'summary.json',dict(rows=rows,qualified_phy=False,backend_admitted=False))
 save(out/'state.json',dict(status='complete',qualified_phy=False))
 print(out,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('path',type=Path);a=p.parse_args()
 (prepare if a.action=='prepare' else run)(a.path.resolve())
