#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture OpenPLL's existing checked-reuse Xyce without changing OpenPLL."""
import argparse,hashlib,json,re,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent.parent/'OpenPLL/build/tools/xyce_umfpack_value_gather_001'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def copy():
 a=json.loads((SOURCE/'assessment.json').read_text());h=sha(SOURCE/'Xyce')
 if h!=a['binary_sha256']:raise ValueError('OpenPLL binary changed')
 out=ROOT/'build/tools/openpll-xyce-300-v1'/(h[:16]+'-r2');out.mkdir(parents=True,exist_ok=False)
 files=['Xyce','assessment.json','manifest.json','N_LAS_OpenPLLUMFPACKSolver.h','CheckedUMFPACK.h','diode.patch','factory.patch','NLS_context.patch']
 for n in files:shutil.copyfile(SOURCE/n,out/n)
 if sha(out/'Xyce')!=h:raise ValueError('Copy differs')
 (out/'Xyce').chmod(0o755)
 receipt=dict(source=str(SOURCE),source_repository_commit=subprocess.check_output(['git','-C',str(SOURCE.parents[2]),'rev-parse','HEAD'],text=True).strip(),
  files={n:sha(out/n) for n in files},script_sha256=sha(__file__),modified_solver=True,checked_reuse='value-gather',qualified_phy=False)
 (out/'copy.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out,flush=True)
def probe(out):
 c=json.loads((out/'copy.json').read_text())
 if (out/'runtime.json').exists():raise ValueError('Retain existing runtime receipt')
 for n,h in c['files'].items():
  if sha(out/n)!=h:raise ValueError('Captured binary metadata changed')
 rows=[]
 for label,binary in [('stock',Path('/opt/xyce/bin/Xyce')),('umfpack',out/'Xyce')]:
  v=subprocess.run([str(binary),'-v'],capture_output=True,text=True,check=True)
  cap=subprocess.run([str(binary),'-capabilities'],capture_output=True,text=True,check=True)
  ld=subprocess.run(['ldd',str(binary)],capture_output=True,text=True,check=True)
  if 'not found' in ld.stdout:raise ValueError('Missing runtime library')
  libs={str(p):sha(p) for p in {Path(n).resolve() for n in re.findall(r'(?:=>\s+|^\s*)(/[^\s]+)\s+\(',ld.stdout,re.M)}}
  rows.append(dict(label=label,binary=str(binary),sha256=sha(binary),version=v.stdout+v.stderr,capabilities=cap.stdout+cap.stderr,libraries=libs,ldd=ld.stdout))
 result=dict(copy_receipt_sha256=sha(out/'copy.json'),runtimes=rows,production_ngspice_descriptor_sha256=sha(ROOT/'build/tools/ngspice.json'),qualified_phy=False)
 (out/'runtime.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'runtime.json',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['copy','probe']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
 if a.action=='copy':copy()
 else:probe(a.artifact.resolve())
