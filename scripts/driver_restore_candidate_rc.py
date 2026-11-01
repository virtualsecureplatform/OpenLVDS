#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract and independently audit a diagnostic analog driver GDS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from audit_rc import collapse
from extract import extract
from layout import ROOT
from lvs_utils import strict_setup,clean_match


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path,value):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temp.replace(path)


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/driver_layout'):raise ValueError('Use an isolated driver layout')
    physical=json.loads((out/'summary.json').read_text());name='openlvds_driver_core';info=physical['designs'][name]
    if not physical['passed'] or digest(out/'candidate.spice')!=physical['source_sha256']:raise ValueError('Physical driver source changed')
    if any(digest(out/name)!=stamp for name,stamp in physical['files'].items()):
        raise ValueError('Driver geometry or original physical reports changed')
    for n,h in physical['identity']['code'].items():
        if digest(ROOT/'scripts'/n)!=h:raise ValueError('Physical driver producer changed')
    gds=ROOT/info['gds'];path=out/'extraction.json';cached=json.loads(path.read_text()) if path.exists() else {}
    fingerprint=hashlib.sha256(gds.read_bytes()+(ROOT/'scripts/extract.py').read_bytes()).hexdigest()
    if not (cached.get('passed') and cached.get('fingerprint')==fingerprint and
            cached.get('source_sha256')==physical['source_sha256'] and digest(ROOT/cached['netlist'])==cached['netlist_sha256']):
        cached=extract(name,gds,physical['source_sha256'],info['ports'],info['lvs_source_sha256']);atomic(path,cached)
    if not cached['passed']:raise ValueError('Driver extraction failed')
    audit=out/'rc_audit';audit.mkdir(exist_ok=True);network=ROOT/cached['netlist']
    net=audit/'wire_collapsed.spice';net.write_text(collapse(network.read_text()))
    schematic=gds.with_suffix('.sch.spice')
    if digest(schematic)!=info['lvs_source_sha256']:raise ValueError('Driver schematic changed')
    setup=strict_setup(audit/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
    report=audit/'lvs.log'
    result=subprocess.run(['netgen','-batch','lvs',f'{net} {name}',f'{schematic} {name}',str(setup),str(report)],
                          cwd=audit,capture_output=True,text=True)
    (audit/'console.log').write_text(result.stdout+result.stderr)
    passed=clean_match(report.read_text() if report.exists() else '',result.returncode)
    atomic(out/'rc_audit.json',dict(passed=passed,netlist_sha256=digest(network),gds_sha256=digest(gds),
        source_sha256=physical['source_sha256'],report=str(report.relative_to(ROOT)),report_sha256=digest(report)))
    print(json.dumps(dict(output=str(out),passed=passed)),flush=True);return 0 if passed else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layout',type=Path);a=p.parse_args();raise SystemExit(run(a.layout.resolve()))
