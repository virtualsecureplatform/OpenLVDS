#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract and audit an isolated DLL layout without modifying active manifests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from audit_rc import collapse
from extract import extract
from lvs_utils import strict_setup,clean_match

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layout',type=Path);a=p.parse_args()
    out=a.layout.resolve();m=json.loads((out/'summary.json').read_text())
    if not m.get('passed'):raise ValueError('Candidate DRC/LVS failed')
    name='openlvds_dll_analog';info=m['designs'][name];gds=ROOT/info['gds']
    if digest(out/'candidate.spice')!=m['source_sha256']:raise ValueError('Candidate source changed')
    extraction=out/'extraction.json'
    cached=json.loads(extraction.read_text()) if extraction.exists() else {}
    extractor_hash=hashlib.sha256(gds.read_bytes()+Path(__file__).with_name('extract.py').read_bytes()).hexdigest()
    valid=bool(cached.get('passed') and cached.get('gds_sha256')==digest(gds) and
        cached.get('fingerprint')==extractor_hash and cached.get('source_sha256')==m['source_sha256'] and
        (ROOT/cached.get('netlist','missing')).is_file())
    if valid:valid=digest(ROOT/cached['netlist'])==cached['netlist_sha256']
    if not valid:
        cached=extract(name,gds,m['source_sha256'],info['ports'],info['lvs_source_sha256'])
        extraction.write_text(json.dumps(cached,indent=2)+'\n')
    if not cached.get('passed'):raise ValueError('RC extraction failed')
    audit=out/'rc_audit';audit.mkdir(exist_ok=True)
    raw=ROOT/cached['netlist'];net=audit/'wire_collapsed.spice';net.write_text(collapse(raw.read_text()))
    schematic=gds.with_suffix('.sch.spice')
    if digest(schematic)!=info['lvs_source_sha256']:raise ValueError('LVS source changed')
    setup=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    local=strict_setup(audit/'setup.tcl',setup);report=audit/'lvs.log'
    r=subprocess.run(['netgen','-batch','lvs',f'{net} {name}',f'{schematic} {name}',str(local),str(report)],cwd=audit,capture_output=True,text=True)
    (audit/'console.log').write_text(r.stdout+r.stderr)
    passed=clean_match(report.read_text() if report.exists() else '',r.returncode)
    result=dict(passed=passed,netlist_sha256=digest(raw),gds_sha256=digest(gds),source_sha256=m['source_sha256'],
        schematic_sha256=digest(schematic),report=str(report.relative_to(ROOT)),report_sha256=digest(report) if report.exists() else None)
    (out/'rc_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
