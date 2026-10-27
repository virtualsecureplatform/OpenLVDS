#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Short parasitic R, remove parasitic C, and independently LVS the DC topology."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from lvs_utils import clean_match

ROOT=Path(__file__).resolve().parents[1]

def collapse(text):
    parents={}
    def root(n):
        parents.setdefault(n,n)
        if parents[n]!=n:parents[n]=root(parents[n])
        return parents[n]
    lines=text.splitlines();ports=[];header=False
    for line in lines:
        w=line.split()
        if not w:continue
        if w[0].lower()=='.subckt':ports+=w[2:];header=True
        elif w[0]=='+':
            if header:ports+=w[1:]
        else:header=False
        if w[0][0].lower()=='r' and len(w)==4:
            a,b=root(w[1]),root(w[2]);parents[b]=a
    named={}
    for p in ports:
        r=root(p)
        if r in named and named[r]!=p:raise ValueError('RC network shorts distinct formal ports')
        named[r]=p
    def node(n):return named.get(root(n),root(n))
    result=[]
    for line in lines:
        w=line.split()
        if w and w[0][0].lower() in ['r','c'] and len(w)==4:continue
        if w and w[0][0].lower()=='x':
            end=next((i for i,v in enumerate(w) if '=' in v),len(w))
            w[1:end-1]=[node(n) for n in w[1:end-1]];line=' '.join(w)
        result.append(line)
    return '\n'.join(result)+'\n'

def main():
    p=argparse.ArgumentParser();p.add_argument('--design',default='openlvds_driver_core,openlvds_dll_analog,openlvds_delay_line,openlvds_receiver_core,lvds_bias')
    a=p.parse_args();models=json.loads((ROOT/'build/extracted/current.json').read_text())['designs']
    physical=json.loads((ROOT/'build/layout/current.json').read_text())['designs'];results={}
    setup=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    for name in a.design.split(','):
        info=models[name];source=ROOT/info['netlist']
        out=ROOT/'build/rc_audit'/info['netlist_sha256'][:12];out.mkdir(parents=True,exist_ok=True)
        net=out/'wire_collapsed.spice';net.write_text(collapse(source.read_text()))
        schematic=(ROOT/physical[name]['gds']).with_suffix('.sch.spice');report=out/'lvs.log'
        r=subprocess.run(['netgen','-batch','lvs',f'{net} {name}',f'{schematic} {name}',str(setup),str(report)],capture_output=True,text=True,cwd=out)
        (out/'console.log').write_text(r.stdout+r.stderr)
        results[name]=dict(passed=clean_match(report.read_text() if report.exists() else '',r.returncode),
            netlist_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),report=str(report.relative_to(ROOT)))
        print(name,'PASS' if results[name]['passed'] else 'FAIL',flush=True)
    summary=dict(passed=all(r['passed'] for r in results.values()),designs=results)
    (ROOT/'build/rc_audit/summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
