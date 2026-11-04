#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent PDK KLayout macro DRC of the complete routed release counter.

Use the actual installed runset with FEOL/BEOL/offgrid/floating-metal enabled.
Macro scope excludes die seal/density; antenna and electrical timing are separate.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import build_static_phase_backend_v3 as physical

ROOT=physical.ROOT
VERSION='whole-native-static-counter-pdk-klayout-drc-v2.1'
CONTEXT='static_phase_klayout_v2'
sha=physical.sha
OPTIONS=dict(feol='true',beol='true',offgrid='true',floating_met='true',sram_exclude='false',seal='false',thr='2')


def parse_report(path,top):
    root=ET.parse(path).getroot()
    if root.tag!='report-database' or root.find('items') is None:raise ValueError('Incomplete KLayout report structure')
    declared=root.findtext('top-cell')
    if declared!=top:raise ValueError('KLayout report top-cell mismatch')
    items=root.find('items').findall('item');counts=Counter()
    for item in items:
        category=item.findtext('category');cell=item.findtext('cell')
        if not category or not cell or item.find('values') is None:raise ValueError('Incomplete KLayout violation record')
        counts[category]+=1
    return dict(violation_count=len(items),violations_by_category=dict(counts),top_cell=declared)


def tool():
    path=shutil.which('klayout')
    if path is None:raise ValueError('Use the established tools environment')
    p=subprocess.run([path,'-b','-v'],capture_output=True,text=True,check=True)
    return dict(path=path,sha256=sha(Path(path)),resolved_path=str(Path(path).resolve()),version=(p.stdout+p.stderr).strip())


def prepare(parent):
    m=physical.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if not r['passed'] or len(r['rows'])!=1:raise ValueError('Require clean complete native counter')
    row=r['rows'][0];folder=parent/physical.NAME;gds=folder/(physical.NAME+'.gds')
    if row['macro']!=physical.NAME or row['drc_count']!='0' or not row['lvs_passed'] or sha(gds)!=row['gds_sha256']:raise ValueError('Counter physical witness changed')
    runset=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/klayout/drc/sky130A_mr.drc'
    text=runset.read_text()
    for variable in ['input','top_cell','report',*OPTIONS]:
        if '$'+variable not in text:raise ValueError('Installed runset option missing: '+variable)
    paths=[parent/n for n in ['manifest.json','summary.json','state.json']]+[gds,folder/(physical.NAME+'.sch.spice'),folder/(physical.NAME+'.lvs.log')]
    code=[Path(__file__),Path(physical.__file__)]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),gds=str(gds.relative_to(ROOT)),top=physical.NAME,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={str(p.relative_to(ROOT)):sha(p) for p in code},
        runset=str(runset),runset_sha256=sha(runset),options=OPTIONS,tool=tool(),
        scope='Installed full macro FEOL/BEOL/offgrid/floating-metal rules, no SRAM exclusion; no die seal/density, antenna, electrical or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['options']!=OPTIONS
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items()) or sha(Path(i['runset']))!=i['runset_sha256']
        or tool()!=i['tool']):raise ValueError('Independent KLayout context changed')
    physical.bound(ROOT/i['parent']);return m


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior independent DRC run')
        (out/'state.json').write_text('{"status":"checking","qualified_phy":false}\n')
        args=[i['tool']['path'],'-b','-zz','-r',i['runset']]
        for k,v in dict(input=str(ROOT/i['gds']),top_cell=i['top'],report=str(out/'report.lyrdb'),**i['options']).items():args += ['-rd',k+'='+v]
        (out/'command.json').write_text(json.dumps(args,indent=2)+'\n')
        with (out/'console.log').open('w') as log:p=subprocess.run(args,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        error=None;report=None
        try:
            if p.returncode:raise ValueError('KLayout process failed: '+str(p.returncode))
            report=parse_report(out/'report.lyrdb',i['top'])
            log=(out/'console.log').read_text()
            for flag in ['feol','beol','floating_met','offgrid']:
                if flag+': true' not in log:raise ValueError('Runset did not confirm enabled '+flag)
            bound(out)
        except Exception as e:error=str(e)
        result=dict(report or {},returncode=p.returncode,error=error,passed=error is None and report['violation_count']==0,
            qualified_phy=False,files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['summary.json','state.json','.execution.lock']},scope=i['scope'])
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='independent_drc_complete',passed=result['passed'],qualified_phy=False))+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
