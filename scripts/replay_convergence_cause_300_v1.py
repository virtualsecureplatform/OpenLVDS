#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only replay of completed convergence experiments and causal control."""
import hashlib,json,math,re
from collections import Counter
from pathlib import Path
import numpy as np
from native_binary_raw_v2 import validate
from analyze_step_trace_v361 import analyze

ROOT=Path(__file__).resolve().parents[1]
BANK=ROOT/'build/diagnostics/bank_convergence_cause_300_v1/c8567c8e71b2e6cb'
DECODER=ROOT/'build/diagnostics/convergence_cause_300_v1/dfc0ac82cef11ba4'
CENTER=ROOT/'build/diagnostics/supply_current_centering_v362/508e395be9fbc556'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def replay():
 inputs={}
 def bind(p,expected=None):
  h=sha(p)
  if expected is not None and h!=expected:raise ValueError('Changed retained input: '+str(p))
  inputs[str(p)]=h
 def retained(p):
  bind(p/'manifest.json');bind(p/'summary.json');bind(p/'state.json')
  if json.loads((p/'state.json').read_text())['status']!='complete':raise ValueError('Producer not terminal')
  result=json.loads((p/'summary.json').read_text())
  for row in result['rows']:
   folder=p/row['task']['id'];bind(folder/'summary.json')
   if row!=json.loads((folder/'summary.json').read_text()):raise ValueError('Producer row mismatch')
   for n,h in row['files'].items():bind(folder/n,h)
  return result,json.loads((p/'manifest.json').read_text())
 b,bm=retained(BANK);d,dm=retained(DECODER);c,cm=retained(CENTER)
 for m in (bm,dm):
  for n,h in m['identity']['model_inputs'].items():bind(Path(n),h)
 bank=ROOT/cm['identity']['parent']/'bank.spice'
 bind(bank);bind(BANK/'bank.spice',sha(bank))
 # Historical current-centering sources and models must still match their capture.
 for n,h in cm['identity']['inputs'].items():bind(ROOT/n,h)
 for p in (Path(__file__),ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/analyze_step_trace_v361.py'):bind(p)
 names,base=validate(BANK/'0/bench.raw',set(bm['names']),200e-12)
 comparisons=[]
 for k in (1,2):
  ns,w=validate(BANK/str(k)/'bench.raw',set(names),200e-12)
  if ns!=names or not np.array_equal(base,w):raise ValueError('Observer changes complete bank trace')
  comparisons.append(dict(case=k,records=len(w),identical_all_voltages_and_time=True))
 log=(BANK/'2/ngspice.log').read_text();steps=analyze(log);failures=[];dc_failures=0
 for line in log.splitlines():
  if not line.startswith('OLVDS_CONV '):continue
  r=dict(t.split('=',1) for t in line.split()[1:])
  if float(r['t'])==0:dc_failures+=1;continue
  if not 0<float(r['t'])<=200e-12:raise ValueError('Out-of-scope failure')
  old,new=float(r['old']),float(r['new']);delta=abs(new-old)
  tol=1e-4*max(abs(old),abs(new))+1e-12
  if r['node']!='vdd#branch' or r['type']!='4':raise ValueError('Different failing equation observed')
  if not math.isclose(float(r['delta']),delta,rel_tol=1e-12) or not math.isclose(float(r['tolerance']),tol,rel_tol=1e-12):raise ValueError('Convergence arithmetic mismatch')
  if not delta>tol:raise ValueError('Logged equation did not fail')
  failures.append(r)
 if len(failures)!=49964 or not steps['positive_time_counts']['noncon_reject']==458 or steps['truncation_rejections'] or steps['positive_time_counts'].get('charge_trunc',0):raise ValueError('Different bank mechanism')
 ratio=np.array([float(r['ratio']) for r in failures])
 direct=dict(positive_failures=len(failures),dc_failures=dc_failures,nodes=dict(Counter(r['node'] for r in failures)),
  current_equation_tolerance_arithmetic_verified=True,ratio_min=float(ratio.min()),ratio_median=float(np.median(ratio)),ratio_max=float(ratio.max()),
  last_logged_ps=float(failures[-1]['t'])*1e12,log_capped=True,last_example=failures[-1],steps=steps)
 centered=[]
 for k in (0,1):
  ns,w=validate(CENTER/str(k)/'bench.raw',set(names),200e-12)
  if set(ns)!=set(names):raise ValueError('Centered vector set differs')
  errors=[float(np.max(np.abs(np.interp(base[:,0],w[:,0],w[:,ns.index(n)])-base[:,j]))) for j,n in enumerate(names) if n!='time']
  dc=max(abs(float(w[0,ns.index(n)]-base[0,j])) for j,n in enumerate(names) if n!='time')
  if max(errors)>1e-6 or dc>1e-6:raise ValueError('Current-centering changes bank voltages')
  centered.append(dict(case=k,records=len(w),maximum_voltage_error_v=max(errors),maximum_dc_error_v=dc))
 trace=analyze((CENTER/'1/ngspice.log').read_text())
 if trace['positive_time_counts'].get('ni_limit',0) or trace['positive_time_counts'].get('noncon_reject',0):raise ValueError('Centering did not remove rejections')
 cn,cw=validate(DECODER/'0/bench.raw',{'v(vdd)','v(x)','v(y)'},200e-12)
 for k in (1,2,3):
  ns,w=validate(DECODER/str(k)/'bench.raw',set(cn),200e-12)
  if ns!=cn or not np.array_equal(cw,w):raise ValueError('Decoder differs between variants')
 # Preserve the original baseline-report indexing bug; independently validate its raw above.
 decoder=dict(all_four_traces_identical=True,records=len(cw),baseline_reporting_error=d['rows'][0].get('validation_error'),
  baseline_raw_independently_complete=True,positive_transient_failures=0)
 for k in (2,3):
  for l in (DECODER/str(k)/'ngspice.log').read_text().splitlines():
   if l.startswith('OLVDS_CONV ') and float(dict(t.split('=',1) for t in l.split()[1:])['t'])>0:raise ValueError('Decoder has transient failure')
 diode_log=(DECODER/'4/ngspice.log').read_text()
 if d['rows'][4]['returncode']==0 or 'Timestep too small' not in diode_log:raise ValueError('Diode control did not reproduce failure')
 _,dw=validate(DECODER/'5/bench.raw',{'v(node)'},5e-9)
 result=dict(inputs=inputs,bank_observer_comparisons=comparisons,direct=direct,current_centering=centered,
  centered_positive_iteration_limits=0,centered_positive_rejections=0,decoder=decoder,
  diode=dict(original_aborts=True,patched_complete_records=len(dw),patched_final_time=float(dw[-1,0])),
  conclusion='Captured quiet-bank slowdown is dominated by repeated failure of the VDD source-current iterate convergence norm, causing 100-iteration attempts and timestep rejection. Standalone diode sidewall bug is separately reproduced but absent from this bank device path.',
  limitations='Direct failure logging caps at 150.328 ps of the complete 200 ps trace. Origin of current-iterate variation (matrix conditioning, cancellation or model behavior) is not established. This is not a universal fix or PHY admission.',qualified_phy=False)
 out=ROOT/'build/reports/convergence_cause_replay_300_v1';out.mkdir(exist_ok=False)
 (out/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','direct')},indent=2));print('direct:',json.dumps(direct));print(out,flush=True)

if __name__=='__main__':replay()
