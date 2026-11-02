#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract and independently audit only a DRC/LVS-qualified compact driver GDS."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess

from audit_rc import collapse
from extract import extract
from lvs_utils import strict_setup, clean_match
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_driver_core'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/driver_compact_layout'):
        raise ValueError('Require isolated compact-driver physical evidence')
    physical=json.loads((parent/'summary.json').read_text())
    info=physical['designs'][TOP]
    if (physical['passed'] is not True or info['passed'] is not True or
            info['drc_count']!='0' or info['lvs_passed'] is not True or
            parent.name!=hashlib.sha256(json.dumps(physical['identity'],sort_keys=True).encode()).hexdigest()[:16] or
            sha(parent/'candidate.spice')!=physical['source_sha256']):
        raise ValueError('Require admitted physical driver before RC extraction')
    gds=ROOT/info['gds']
    technology=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    identity=dict(parent=str(parent.relative_to(ROOT)),physical_sha256=sha(parent/'summary.json'),
        gds_sha256=sha(gds),source_sha256=physical['source_sha256'],
        code={n:sha(ROOT/'scripts'/n) for n in ['extract_driver_compact.py','extract.py','reduce_rc.py','audit_rc.py','lvs_utils.py','receiver_static_diagnosis.py']},
        netgen_technology=dict(path=str(technology),sha256=sha(technology)),
        scope='Native GDS distributed RC plus independent wire-collapsed LVS; no electrical or PHY admission.')
    out=ROOT/'build/diagnostics/driver_compact_extraction'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)

    def unchanged():
        if (sha(parent/'summary.json')!=identity['physical_sha256'] or
                any(sha(parent/n)!=h for n,h in physical['files'].items()) or
                any(sha(ROOT/n)!=h for n,h in physical['identity']['inputs'].items()) or
                any(sha(ROOT/'scripts'/n)!=h for n,h in physical['identity']['code'].items()) or
                any(sha(Path(n))!=h for n,h in physical['identity']['technology'].items()) or
                any(sha(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()) or sha(technology)!=identity['netgen_technology']['sha256']):
            raise ValueError('Compact driver physical/extraction context changed')

    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        unchanged()
        if (out/'summary.json').exists():
            r=json.loads((out/'summary.json').read_text())
            if r['identity']!=identity or any(sha(ROOT/n)!=h for n,h in r['files'].items()):
                raise ValueError('Compact driver extraction outputs changed')
            return out
        if (out/'manifest.json').exists(): raise ValueError('Prior partial extraction retained')
        capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False))
        extraction=extract(TOP,gds,physical['source_sha256'],info['ports'],info['lvs_source_sha256'])
        capture_manifest(out/'extraction.json',extraction)
        if not extraction['passed']: raise ValueError('Native compact-driver RC extraction failed')
        network=ROOT/extraction['netlist']
        net=out/'wire_collapsed.spice';net.write_text(collapse(network.read_text()))
        schematic=parent/(TOP+'.sch.spice')
        if sha(schematic)!=info['lvs_source_sha256']: raise ValueError('Driver LVS source changed')
        setup=strict_setup(out/'setup.tcl',technology)
        report=out/'lvs.log'
        result=subprocess.run(['netgen','-batch','lvs',f'{net} {TOP}',f'{schematic} {TOP}',str(setup),str(report)],
                              cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(result.stdout+result.stderr)
        passed=clean_match(report.read_text() if report.exists() else '',result.returncode)
        unchanged()
        paths=[p for p in out.iterdir() if p.is_file() and p.name not in ['.execution.lock','summary.json']]
        paths += [network,ROOT/extraction['raw_netlist'],(ROOT/extraction['raw_netlist']).parent/'summary.json']
        capture_manifest(out/'summary.json',dict(identity=identity,passed=passed,extraction=extraction,
            rc_audit=dict(passed=passed,report=str(report.relative_to(ROOT)),report_sha256=sha(report),netlist_sha256=sha(network)),
            files={str(p.relative_to(ROOT)):sha(p) for p in paths},qualified_phy=False,physical_admission=False))
        print('Compact driver RC audit:',passed,flush=True)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);a=p.parse_args()
    print(run(a.parent.resolve()),flush=True)
