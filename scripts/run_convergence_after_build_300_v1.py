#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Wait for one verified build identity, then queue the frozen cause experiment."""
import argparse,json,time
from pathlib import Path
import probe_convergence_cause_300_v1 as probe

def follow(build,pid,start_ticks):
 proc=Path('/proc')/str(pid)
 while not (build/'summary.json').exists():
  try:fields=(proc/'stat').read_text().split()
  except FileNotFoundError:raise RuntimeError('Build exited without a completed receipt; preserve failure')
  if fields[21]!=start_ticks or fields[2]=='Z':raise RuntimeError('Original build identity is terminal or changed')
  time.sleep(5)
 artifact=probe.prepare(build)
 probe.save(artifact/'dispatch.json',dict(build_pid=pid,build_start_ticks=start_ticks,qualified_phy=False))
 probe.run(artifact)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('build',type=Path);p.add_argument('pid',type=int);p.add_argument('start_ticks');a=p.parse_args()
 follow(a.build.resolve(),a.pid,a.start_ticks)
