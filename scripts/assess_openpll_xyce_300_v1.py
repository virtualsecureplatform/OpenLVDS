#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Await the original producer, then verify complete backend comparisons."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def follow(out,pid,birth):
 while not (out/'summary.json').exists():
  try:s=(Path('/proc')/str(pid)/'stat').read_text().split()
  except FileNotFoundError:raise RuntimeError('Original producer exited without summary')
  if s[21]!=birth or s[2]=='Z':raise RuntimeError('Original producer identity ended')
  time.sleep(5)
 artifact='/work/OpenLVDS/'+str(out.relative_to(ROOT))
 subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/assess_openpll_xyce_300_v1.py','report',artifact],cwd=ROOT,check=True)
def report(out):
 from benchmark_openpll_xyce_300_v1 import compare,REFERENCE,RUNTIME
 from native_binary_raw_v2 import validate
 m=json.loads((out/'manifest.json').read_text());i=m['identity'];s=json.loads((out/'summary.json').read_text())
 if json.loads((out/'state.json').read_text())['status']!='complete' or len(s['rows'])!=len(m['tasks']):raise ValueError('Campaign not terminal')
 if (out/'assessment.json').exists():raise ValueError('Retain prior assessment')
 pins={str(ROOT/'scripts/benchmark_openpll_xyce_300_v1.py'):i['script_sha256'],**i['helpers'],**i['models'],**i['source_files']}
 pins[str(RUNTIME/'runtime.json')]=i['runtime_sha256']
 pins[str(ROOT/'build/tools/ngspice.json')]=i['production_sha256']
 pins.update({str(out/n):h for n,h in m['libraries'].items()})
 pins.update({str(out/n):sha(out/n) for n in ('manifest.json','summary.json','state.json')})
 pins[str(Path(__file__).resolve())]=sha(__file__)
 for r in i['runtime']['runtimes']:pins.update({r['binary']:r['sha256'],**r['libraries']})
 rows=[]
 for task,stored in zip(m['tasks'],s['rows']):
  folder=out/task['id'];pins[str(folder/'summary.json')]=sha(folder/'summary.json')
  if stored!=json.loads((folder/'summary.json').read_text()) or stored['task']!=task:raise ValueError('Stored case differs')
  pins[str(folder/'bench.cir')]=task['deck_sha256']
  pins.update({str(folder/n):h for n,h in stored['files'].items()})
  row={k:stored[k] for k in ('task','complete','returncode','wall_seconds','child_cpu_seconds','model_version_substitutions','warning_occurrences')}
  if 'error' in stored:row['error']=stored['error']
  if stored['complete'] and 'error' not in stored:
   validate(folder/'bench.raw',set(m['names']),task['stop'])
   ref=REFERENCE if task['kind']=='quiet' else out/'6/bench.raw'
   comparison=compare(ref,folder/'bench.raw',m['names'],task['stop'],task['kind']=='active')
   if comparison!=stored['comparison']:raise ValueError('Waveform comparison did not reproduce')
   row.update(comparison=comparison,comparison_independently_replayed=True)
   if 'fresh_ngspice_wall_ratio' in stored:row['observed_ngspice_wall_ratio']=stored['fresh_ngspice_wall_ratio']
  rows.append(row)
 for p,h in pins.items():
  if sha(p)!=h:raise ValueError('Changed retained input: '+p)
 result=dict(inputs=pins,rows=rows,all_nine_cases_complete=all(r['complete'] and 'error' not in r for r in rows),
  limitations=['Numeric tolerance values are matched; engine-specific acceptance definitions differ.','Active timing reference uses ABSTOL=1e-9, not a tight-tolerance active reference.','Xyce substitutes BSIM4 versions and may clamp parameters; warning records remain explicit.','Wall times include startup and uncontrolled external machine load.','No production backend switch or PHY qualification is implied.'],qualified_phy=False)
 (out/'assessment.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(rows,indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['follow','report']);p.add_argument('artifact',type=Path);p.add_argument('pid',type=int,nargs='?');p.add_argument('birth',nargs='?');a=p.parse_args()
 if a.action=='follow':follow(a.artifact.resolve(),a.pid,a.birth)
 else:report(a.artifact.resolve())
