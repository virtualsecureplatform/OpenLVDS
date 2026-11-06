#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build measured capacitor references from the mask-bound unrouted diagnostic.

Reference preparation only: no route, bank LVS, joint RC or electrical pass.
The routed-bank pipeline must build its own reference from its actual native
extraction; this unrouted connectivity is never a routed model substitute.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import analyze_measured_bank_fine_junctions_v140 as analysis
import measured_bank_junction_reconstruction_v142 as correction

ROOT=analysis.ROOT
sha=analysis.sha
VERSION='measured-62-capacitor-junction-reference-with-exact-nontarget-preservation-v143.1'
CONTEXT='measured_bank_junction_reference_v143'


def prepare(parent):
    pi,bi=analysis.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or not r['analysis_completed'] or r['geometry']!=pi['geometry'] or r['parameters_changed']
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged complete mask-bound junction diagnostic')
    paths=[parent/'manifest.json',parent/'state.json',parent/'summary.json',*[parent/n for n in r['files']]]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),placement=pi['parent'],profile=pi['profile'],top=bi['graph']['top']+'_flat',
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},scope='Unrouted native measured-capacitor reference preparation only; no routing, bank LVS, joint RC or PHY qualification')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Measured capacitor reference context changed')
    pi,bi=analysis.bound(ROOT/i['parent'])
    if pi['parent']!=i['placement'] or pi['profile']!=i['profile'] or bi['graph']['top']+'_flat'!=i['top']:raise ValueError('Measured reference bank identity changed')
    return i,bi


def run(out):
    i,bi=bound(out);parent=ROOT/i['parent'];top=i['top'];source=parent/'ordinary'/(bi['graph']['top']+'.lvs.spice')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial measured reference')
        (out/'state.json').write_text('{"status":"preparing_reference","qualified_phy":false}\n')
        rows=json.loads((analysis.MEASUREMENTS/'summary.json').read_text())['rows'];original=source.read_text()
        measured,proof=correction.reconstruct(original,top,rows,i['profile'])
        if proof['passive_record_count']!=0:raise ValueError('Ordinary reference unexpectedly contains explicit R/C')
        path=out/'measured_reference.spice';path.write_text(measured)
        repeated,again=correction.reconstruct(measured,top,rows,i['profile'])
        if repeated!=measured or again['corrected_devices']!=0:raise ValueError('Measured junction reference is not byte-idempotent')
        reproduced,second=correction.reconstruct(original,top,rows,i['profile'])
        if reproduced!=measured or second!=proof:raise ValueError('Measured junction correction cannot regenerate exactly')
        original_report=json.loads((parent/'summary.json').read_text());expected=original_report['diagnostic']['summary']['devices_with_mismatch']
        if proof['corrected_devices']!=expected:raise ValueError('Correction differs from measured diagnostic device coverage')
        canonical=(ROOT/i['placement']/'reference.spice').read_text()
        parameters=analysis.physical.inventory.verify(canonical,bi['graph']['top'],correction.collapse(measured),top,i['profile'])
        bound(out)
        r=dict(reference_preparation_passed=True,correction=proof,reference_supplied_native_parameters=parameters,
               correction_regenerates=True,byte_idempotent=True,original_extraction_preserved=True,source_sha256=sha(source),
               measured_reference_sha256=sha(path),routed=False,whole_bank_native_lvs_passed=False,joint_rc_qualified=False,
               electrical_qualification_passed=False,qualified_phy=False,scope=i['scope'])
        r['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","reference_preparation_passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
