#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the installed Magic partial antenna model on the full native counter.

This is explicitly the PDK's partial model (its documented diode-diffusion
limitation is retained), not a claim of cumulative foundry antenna signoff.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import layout
import build_static_phase_backend_v3 as physical

ROOT=physical.ROOT
VERSION='whole-native-static-counter-installed-partial-antenna-v2.1'
CONTEXT='static_phase_antenna_v2'
sha=physical.sha
FLAT='openlvds_static_phase_antenna_flat_v2'


def parse_result(path,ext):
    lines=path.read_text().splitlines()
    if len(lines)!=3 or lines[0]!='0' or not lines[1].isdigit() or lines[2]!='COMPLETE':raise ValueError('Antenna command did not complete successfully')
    text=ext.read_text()
    if not re.search(r'(?m)^tech sky130A\s*$',text):raise ValueError('Antenna extraction technology changed')
    devices=re.findall(r'(?m)^device msubckt sky130_fd_pr__(?:nfet_01v8|pfet_01v8|pfet_01v8_hvt)\s',text)
    if len(devices)!=402:raise ValueError('Antenna check did not cover all 402 native MOS')
    count=int(lines[1]);return dict(feedback_count=count,native_mos_count=len(devices),installed_partial_antenna_passed=count==0)


def prepare(parent):
    m=physical.bound(parent);report=json.loads((parent/'summary.json').read_text())
    if not report['passed'] or len(report['rows'])!=1:raise ValueError('Require the complete clean counter GDS')
    row=report['rows'][0];folder=parent/physical.NAME;gds=folder/(physical.NAME+'.gds')
    if row['macro']!=physical.NAME or sha(gds)!=row['gds_sha256'] or row['drc_count']!='0' or not row['lvs_passed']:raise ValueError('Counter GDS/LVS changed')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/magic';tech=pdk/'sky130A.tech';rc=pdk/'sky130A.magicrc'
    lines=tech.read_text().splitlines();rules=[l.strip() for l in lines if l.strip().startswith(('antenna ','model partial','tiedown '))]
    for required in ['model partial','antenna m1,m2,m3 sidewall 400 2200 400','antenna m4,m5 sidewall 400 2200 400','antenna v3,v4 surface 6 0 36']:
        if required not in rules:raise ValueError('Installed partial antenna coverage changed')
    files=[parent/n for n in ['manifest.json','summary.json','state.json']]+[gds,folder/(physical.NAME+'.sch.spice'),folder/(physical.NAME+'.lvs.log')]
    code=[Path(__file__),Path(physical.__file__),Path(layout.__file__)]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),gds=str(gds.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        code={str(p.relative_to(ROOT)):sha(p) for p in code},pdk_files={str(p):sha(p) for p in [tech,rc]},antenna_rules=rules,tools=physical.native.environment.tools(),
        scope='Installed Magic SKY130 partial antenna model with all native MOS; diode diffusion is not modeled per PDK note, no cumulative/foundry, electrical or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or physical.native.environment.tools()!=i['tools']):raise ValueError('Partial antenna context changed')
    physical.bound(ROOT/i['parent']);return m


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior antenna run')
        (out/'state.json').write_text('{"status":"checking","qualified_phy":false}\n');result=None;error=None
        try:
            body=f'''gds readonly false
gds read {{{ROOT/i['gds']}}}
load {physical.NAME}
flatten {FLAT}
load {FLAT}
extract style ngspice()
extract all
feedback clear
puts "OPENLVDS_PARTIAL_ANTENNA_BEGIN"
set status [catch {{antennacheck}} message]
puts "OPENLVDS_PARTIAL_ANTENNA_RESULT $status $message"
set f [open {{{out/'result.txt'}}} w]
puts $f $status
puts $f [feedback count]
puts $f COMPLETE
close $f
feedback save {{{out/'antenna.feedback'}}}
'''
            layout.invoke_magic(out,body,'antenna')
            result=parse_result(out/'result.txt',out/(FLAT+'.ext'));bound(out)
        except Exception as e:error=str(e)
        report=dict(result or {},error=error,passed=error is None and result['installed_partial_antenna_passed'],qualified_phy=False,
            files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['state.json','summary.json','.execution.lock']},scope=i['scope'])
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='partial_antenna_complete',passed=report['passed'],qualified_phy=False))+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
