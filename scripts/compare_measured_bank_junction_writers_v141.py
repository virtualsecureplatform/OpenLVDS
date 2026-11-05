#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare Magic junction writer policies on one unchanged ordinary extraction.

Experiments write separate netlists. No extraction, geometry or admitted model
is edited; matching a count is not physical junction or RC qualification.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import analyze_measured_bank_fine_junctions_v140 as analysis

ROOT=analysis.ROOT
sha=analysis.sha
VERSION='measured-geometry-versus-magic-junction-writer-options-v141.1'
CONTEXT='measured_bank_junction_writer_v141'
OPTIONS=dict(flat='-J flat',hierarchical='-J hier',distributed='-d -J flat')


def prepare(parent):
    pi,bi=analysis.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or not r['analysis_completed'] or r['parameters_changed'] or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged complete mask-bound fine-section diagnostic')
    name=bi['graph']['top'];ext=parent/'ordinary'/(name+'_flat.ext')
    if not ext.exists() or any(line.startswith('use ') for line in ext.read_text().splitlines()):raise ValueError('Require one fully flattened ordinary extraction')
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',*[parent/n for n in r['files']]]
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profile=pi['profile'],top=name,options=OPTIONS,
           source_ext=str(ext.relative_to(ROOT)),source_ext_sha256=sha(ext),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
           scope='Writer-option comparison on unchanged unrouted ordinary extraction; no model correction, bank LVS, joint RC or electrical admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['options']!=OPTIONS
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Junction writer comparison context changed')
    pi,bi=analysis.bound(ROOT/i['parent']);return i,pi,bi


def signature(text,top):
    ports,devices=analysis.partition.native.native_leaves(text,top)
    return ports,Counter(map(analysis.partition.junctions.topology_key,devices))


def run(out):
    i,pi,bi=bound(out);parent=ROOT/i['parent'];top=i['top']+'_flat'
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial writer comparison')
        (out/'state.json').write_text('{"status":"comparing","qualified_phy":false}\n')
        ext=out/Path(i['source_ext']).name;shutil.copyfile(ROOT/i['source_ext'],ext)
        commands=[]
        for label,option in i['options'].items():commands += ['ext2spice lvs',f'ext2spice {option} -o {label}.spice {ext.name}']
        analysis.physical.legacy.place.layout.invoke_magic(out,'\n'.join(commands),'junction_writers')
        original=re.sub(r'\n[ \t]*\+[ \t]*',' ',(parent/'ordinary'/(i['top']+'.lvs.spice')).read_text())
        source=(ROOT/pi['parent']/'reference.spice').read_text();measurement=json.loads((analysis.MEASUREMENTS/'summary.json').read_text())
        rows=[]
        for label,option in i['options'].items():
            text=re.sub(r'\n[ \t]*\+[ \t]*',' ',(out/(label+'.spice')).read_text())
            if signature(text,top)!=signature(original,top):raise ValueError('Junction writer changed native topology/model/dimensions')
            diagnostic=analysis.partition.diagnose(text,top,measurement['rows']);parameters=error=None
            try:parameters=analysis.physical.inventory.verify(source,i['top'],text,top,i['profile'])
            except ValueError as e:error=str(e)
            rows.append(dict(writer=label,option=option,topology_and_dimensions_preserved=True,
                             capacitor_junction_summary=diagnostic['summary'],per_device_capacitor_junctions_match_geometry=diagnostic['per_device_capacitor_junctions_match_geometry'],
                             reference_parameter_check=parameters,reference_parameter_error=error))
            (out/(label+'_fine_junctions.json')).write_text(json.dumps(diagnostic,indent=2)+'\n')
        if sha(ext)!=i['source_ext_sha256']:raise ValueError('Writer changed the native extraction input')
        bound(out)
        r=dict(analysis_completed=True,rows=rows,source_extraction_unchanged=True,parameters_changed_in_admitted_models=False,
               joint_rc_qualified=False,electrical_qualification_passed=False,qualified_phy=False,scope=i['scope'])
        r['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","analysis_completed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
