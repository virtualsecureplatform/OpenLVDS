#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare measured fine-junction reference data without routing/RC admission."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import analyze_isolated_fine_junctions_v246 as geometry
import isolated_bank_junctions_v251 as correction
import isolated_fine_bank_inventory_v244 as inventory
from verify_measured_balanced_joint_rc_v155 import fine_junctions

ROOT=geometry.ROOT
sha=geometry.sha
VERSION='isolated-bank-measured-fine-junction-reference-only-v252.1'
CONTEXT='isolated_fine_junction_reference_v252'
SCOPE='Geometry-bound selective fine capacitor junction allocation on retained ordinary extraction; unchanged physical bank and all other native/passive records, no routed native LVS/shared-wire RC/timing/PHY admission'


def prepare(parent):
    gi,pi=geometry.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or not r['analysis_completed'] or r['geometry']!=gi['geometry']
        or not r['geometry']['measured_primitive_junction_geometry_bound']
        or not r['geometry']['all_fine_active_regions_separate_between_instances']
        or r['geometry']['fine_instances']!=31 or r['native_census']['native_mos']!=1479 or r['native_census']['native_mims']!=43
        or r['native_census']['newly_characterized_junction_devices']!=155
        or not r['native_census']['native_parameters_preserved']
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require complete exact isolated-bank geometry and native-reference evidence')
    top=pi['graph']['top'];ordinary=parent/'ordinary'/(top+'.lvs.spice')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]+[ROOT/n for n in gi['inputs']]
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),top=top,ordinary=str(ordinary.relative_to(ROOT)),
        measurements=str(geometry.MEASUREMENTS.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Isolated fine-junction reference context changed')
    return i


def run(out):
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial fine-junction reference')
        (out/'state.json').write_text('{"status":"preparing_reference","qualified_phy":false}\n')
        source=(ROOT/i['ordinary']).read_text();rows=json.loads((ROOT/i['measurements']/'summary.json').read_text())['rows'];top=i['top']
        corrected,proof=correction.reconstruct(source,top+'_flat',rows)
        measured=fine_junctions(corrected,top+'_flat',rows)
        parent=ROOT/i['parent'];params=inventory.verify((parent/'reference.spice').read_text(),top,correction.collapse(corrected),top+'_flat')
        if params['native_primitives']!=1522 or proof['identified_capacitor_mos']!=62:raise ValueError('Isolated native reference coverage changed')
        again,repeated=correction.reconstruct(corrected,top+'_flat',rows)
        if again!=corrected or repeated['corrected_devices']!=0:raise ValueError('Fine correction is not byte-idempotent')
        if correction.reconstruct(source,top+'_flat',rows)!=(corrected,proof):raise ValueError('Fine correction does not regenerate')
        (out/'measured_reference.spice').write_text(corrected);bound(out)
        r=dict(ordinary_reference_prepared=True,correction=proof,all_fine_junctions=measured,native_parameters=params,
            corrected_reference_regenerated=True,correction_byte_idempotent=True,original_extraction_preserved=True,
            whole_bank_native_lvs_passed=False,joint_rc_qualified=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
        r['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
