#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh passive RC and strict topology check for the native parallel BUF8 macro."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import build_clock_buffer_pair_v2 as physical
import extract_native_flat_v4 as rc
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from lvs_utils import strict_setup,clean_match
from spice_library import checked_netlist

ROOT=physical.ROOT
sha=physical.sha
VERSION='native-parallel-buf8-fresh-passive-rc-v2.1'
CONTEXT='clock_buffer_pair_rc_v2'


def parent_row(parent):
    m=physical.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if not r['passed'] or len(r['rows'])!=1:raise ValueError('Require complete clean native clock pair')
    row=r['rows'][0];folder=parent/physical.NAME
    if (row['macro']!=physical.NAME or row['child_instances']!=2 or not row['passed']
        or row['drc_count']!='0' or not row['lvs_passed']
        or sha(folder/(physical.NAME+'.gds'))!=row['gds_sha256']
        or sha(folder/(physical.NAME+'.lef'))!=row['lef_sha256']
        or sha(folder/(physical.NAME+'.sch.spice'))!=row['lvs_source_sha256']):raise ValueError('Clock-pair physical/source witness changed')
    return m,row,folder


def prepare(parent):
    m,_,folder=parent_row(parent);name=physical.NAME
    files=[parent/n for n in ['manifest.json','summary.json','state.json']]
    files += [folder/n for n in ['summary.json',name+'.gds',name+'.lef',name+'.mag',name+'.sch.spice',name+'.lvs.log',name+'.drc_count.txt']]
    files += [Path(__file__),Path(physical.__file__),Path(rc.__file__),ROOT/'scripts/reduce_rc.py',
              ROOT/'scripts/audit_rc.py',ROOT/'scripts/audit_rc_comments_v2.py',ROOT/'scripts/audit_passive_rc_v3.py',
              ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},tools=m['identity']['tools'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or physical.native.environment.tools()!=i['tools']):
        raise ValueError('Parallel clock-buffer RC context changed')
    parent_row(ROOT/i['parent']);return m


def run(out):
    m=bound(out);parent=ROOT/m['identity']['parent'];_,row,source=parent_row(parent);name=physical.NAME
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior clock-pair extraction')
        (out/'state.json').write_text('{"status":"extracting","qualified_phy":false}\n')
        gds=source/(name+'.gds');digest=hashlib.sha256(gds.read_bytes()+Path(rc.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/name).exists():raise ValueError('Retain prior extraction namespace')
        info=rc.extract(name,gds,sha(parent/'manifest.json'),ports=row['ports'],source_scope=sha(source/(name+'.sch.spice')))
        (out/'extraction.json').write_text(json.dumps(info,indent=2)+'\n');matched=False;reduced_passive=False
        if info['passed']:
            text=checked_netlist(info);reduced_passive=audit(text)['elementwise_passive_passed']
            if reduced_passive:
                net=out/'wire_collapsed.spice';net.write_text(collapse(text))
                setup=strict_setup(out/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl');log=out/'lvs.log'
                p=subprocess.run(['netgen','-batch','lvs',f'{net} {name}',f'{source/(name+".sch.spice")} {name}',str(setup),str(log)],
                    cwd=out,capture_output=True,text=True)
                (out/'console.log').write_text(p.stdout+p.stderr);matched=clean_match(log.read_text() if log.exists() else '',p.returncode)
        bound(out);passed=bool(info['passed'] and reduced_passive and matched)
        result=dict(extraction=info,rc_topology_passed=matched,reduced_passivity_passed=reduced_passive,passed=passed,
            qualified_phy=False,electrical_qualification_passed=False,
            scope='Fresh native parallel BUF8 and real shared-wire RC/passivity/DC topology only; no phase timing, clock-island or PHY admission')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='clock_pair_rc_complete',passed=passed,qualified_phy=False))+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
