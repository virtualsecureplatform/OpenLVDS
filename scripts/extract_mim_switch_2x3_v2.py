#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh GDS RC and independent DC-topology audit for a DRC/LVS-clean unit.

This does not publish active models or qualify array/pulse timing. Intentional
MIM devices remain in the collapsed audit; only parasitic R/C are collapsed.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import build_mim_switch_2x3_v2 as physical
import extract as rc
from audit_rc import collapse
from lvs_utils import strict_setup,clean_match
from spice_library import checked_netlist

ROOT=physical.ROOT
NAME=physical.unit.NAME
sha=physical.sha
VERSION='mim-switch-2x3-native-rc-audit-v2.1'


def source(parent):
    physical.bound(parent);report=json.loads((parent/'summary.json').read_text())
    if (not report['unit_physical_passed'] or not report['passed'] or report['drc_count']!='0'
        or report['lvs_passed'] is not True or report['qualified_phy'] is not False
        or sha(parent/(NAME+'.sch.spice'))!=report['lvs_source_sha256']
        or sha(parent/(NAME+'.lvs.log'))!=report['lvs_report_sha256']):
        raise ValueError('Require an unchanged DRC/LVS-clean unit prototype')
    return report


def prepare(parent):
    source(parent)
    files=[Path(__file__),Path(physical.__file__),Path(rc.__file__),ROOT/'scripts/audit_rc.py',
           ROOT/'scripts/reduce_rc.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    names=['manifest.json','summary.json','state.json',NAME+'.gds',NAME+'.lef',NAME+'.mag',
           NAME+'.sch.spice',NAME+'.lvs.spice',NAME+'.lvs.log',NAME+'.drc_count.txt',NAME+'.drc.txt']
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):sha(p) for p in files},parent=str(parent.relative_to(ROOT)),
        parent_files={str((parent/n).relative_to(ROOT)):sha(parent/n) for n in names})
    out=ROOT/'build/diagnostics/mim_switch_2x3_rc_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/mim_switch_2x3_rc_v2') or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=v for n,v in {**i['code'],**i['parent_files']}.items())):
        raise ValueError('Unit extraction inputs changed')
    report=source(ROOT/i['parent']);return m,report


def run(out):
    m,report=bound(out);parent=ROOT/m['identity']['parent'];gds=parent/(NAME+'.gds')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior RC execution')
        digest=hashlib.sha256(gds.read_bytes()+Path(rc.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists():raise ValueError('Retain existing RC namespace')
        (out/'state.json').write_text(json.dumps(dict(status='extracting',qualified_phy=False))+'\n')
        info=rc.extract(NAME,gds,sha(parent/'manifest.json'),ports=report['ports'],
            source_scope=sha(parent/(NAME+'.sch.spice')))
        (out/'extraction.json').write_text(json.dumps(info,indent=2)+'\n')
        audit=False
        if info['passed']:
            collapsed=out/'wire_collapsed.spice';collapsed.write_text(collapse(checked_netlist(info)))
            setup=strict_setup(out/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
            log=out/'lvs.log'
            proc=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {NAME}',
                f'{parent/(NAME+".sch.spice")} {NAME}',str(setup),str(log)],cwd=out,capture_output=True,text=True)
            (out/'netgen.log').write_text(proc.stdout+proc.stderr)
            audit=clean_match(log.read_text() if log.exists() else '',proc.returncode)
        bound(out)
        summary=dict(extraction=info,rc_topology_passed=audit,passed=bool(info['passed'] and audit),
            qualified_phy=False,electrical_qualification_passed=False,
            scope='Isolated-unit distributed RC and wire-collapsed topology only; no array, PVT or clock timing admission')
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='unit_rc_complete',passed=summary['passed'],qualified_phy=False))+'\n')
        return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(json.dumps(run(out),indent=2),flush=True)
