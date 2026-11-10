#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe host build identity, then invoke diagnostics inside Apptainer."""
import argparse,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def follow(build,pid,start_ticks):
 proc=Path('/proc')/str(pid)
 while not (build/'summary.json').exists():
  try:fields=(proc/'stat').read_text().split()
  except FileNotFoundError:raise RuntimeError('Build exited without receipt')
  if fields[21]!=start_ticks or fields[2]=='Z':raise RuntimeError('Original build identity ended or changed')
  time.sleep(5)
 prefix=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','scripts/probe_convergence_cause_300_v1.py']
 container='/work/OpenLVDS/'+str(build.relative_to(ROOT))
 p=subprocess.run(prefix+['prepare',container],cwd=ROOT,capture_output=True,text=True,check=True)
 print(p.stdout,flush=True)
 artifact=p.stdout.strip().splitlines()[-1]
 if not artifact.startswith('/work/OpenLVDS/build/diagnostics/convergence_cause_300_v1/'):raise ValueError('Unexpected artifact')
 subprocess.run(prefix+['run',artifact],cwd=ROOT,check=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('build',type=Path);p.add_argument('pid',type=int);p.add_argument('start_ticks');a=p.parse_args();follow(a.build.resolve(),a.pid,a.start_ticks)
