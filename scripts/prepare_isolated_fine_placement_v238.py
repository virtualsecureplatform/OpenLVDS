#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Place the native isolated fine stage without bank electrical admission."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import klayout.db as db
import prepare_balanced_placement_v129 as stock
import build_isolated_fine_cell_views_v236 as views
import isolated_fine_bank_physical_v239 as design

ROOT=stock.ROOT
sha=views.sha
VERSION='isolated-fine-bank-native-graph-and-real-master-placement-v238.1'
CONTEXT='isolated_fine_placement_v238'
BASE=ROOT/'build/diagnostics/balanced_placement_v129/a158104d2fd54d99'
VIEWS=ROOT/'build/diagnostics/isolated_fine_cell_views_v236/b040d127238a22fa'
PILOT=ROOT/'build/diagnostics/discharge_isolated_fine_bank_v220/9e4d0f5b90541807'
SCOPE='Native isolated P20/N16 fine-stage graph and placement feasibility with M4 driver accesses; no routing, shared-wire RC, timing selection, full clock-chain or PHY admission'


def checked(parent,producer,flag):
    i=producer.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or r.get(flag) is not True or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged qualified native physical source')
    return i,r


def inputs():
    pi,pr=checked(BASE,stock,'placement_feasibility_passed')
    vi,vr=checked(VIEWS,views,'canonical_component_views_passed')
    pm=json.loads((PILOT/'manifest.json').read_text());component=PILOT/'p20n16_c1/bank.spice'
    if sha(component)!=pm['libraries']['p20n16_c1']:raise ValueError('Native component pilot library changed')
    # Consume only the immutable DUT definition; live/pending pilot results
    # are neither read nor used to admit this exploratory placement.
    records={**pi['records'],**vr['cells']};g=design.graph(pi['graph']);plan=design.placement(pi['plan'],g,records)
    reference=design.original.native_source(g,[(BASE/'reference.spice').read_text(),
        *[(VIEWS/'native'/model/(model+'.sch.spice')).read_text() for model in (design.DRIVER,design.BUFFER)]])
    proof=design.compare_component(g,component.read_text());proof.update(design.inventory_proof(g,reference,component.read_text()))
    paths=[PILOT/'manifest.json',component,BASE/'reference.spice']
    for parent,i,r in ((BASE,pi,pr),(VIEWS,vi,vr)):
        paths += [parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]
        paths += [ROOT/n for n in {*i['inputs'],*i['code']}]
    return pi,vi,records,g,plan,reference,proof,paths


def prepare():
    pi,vi,records,g,plan,reference,proof,paths=inputs()
    code=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(BASE.relative_to(ROOT)),views=str(VIEWS.relative_to(ROOT)),pilot_library=str((PILOT/'p20n16_c1/bank.spice').relative_to(ROOT)),
        library_parents=[*pi['library_parents'],str(VIEWS.relative_to(ROOT))],graph=g,plan=plan,records=records,graph_proof=proof,
        reference_sha256=hashlib.sha256(reference.encode()).hexdigest(),inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},
        code={str(p.relative_to(ROOT)):sha(p) for p in code},external_files={**pi['external_files'],**vi['external_files']},
        openroad=pi['openroad'],tech_lef=pi['tech_lef'],tools=pi['tools'],klayout=pi['klayout'],scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n')
    (out/'reference.spice').write_text(reference);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or any(sha(Path(t['path']))!=t['sha256'] for t in [i['openroad'],*i['tools'].values()])
        or i['klayout']!=dict(version=db.__version__,module_sha256=sha(Path(db.__file__)))
        or sha(out/'reference.spice')!=i['reference_sha256']):raise ValueError('Isolated placement inputs changed')
    return i


def run(out):
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial isolated placement')
        (out/'state.json').write_text('{"status":"placing","qualified_phy":false}\n')
        error=None;merged=placed=buses=geometry=None
        try:
            merged=stock.merge(out,i);g=i['graph'];plan=i['plan']
            placed=stock.assembly.opendb(out,dict(i,_parent=str(out.relative_to(ROOT))),g,plan)
            file=stock.assembly.gds(out,out,g,plan)
            buses=design.fixed_bus_audit(file,g,plan,i['records']);geometry=stock.assembly.drc(out,file,g['top'])
        except Exception as e:error=type(e).__name__+': '+str(e)
        bound(out);passed=bool(error is None and geometry and geometry['placement_and_fixed_bus_drc_passed'])
        r=dict(graph=i['graph_proof'],merged_library=merged,placement=placed,fixed_buses=buses,placement_geometry=geometry,error=error,
            placement_feasibility_passed=passed,routed=False,whole_bank_lvs_passed=False,joint_rc_extracted=False,
            timing_candidate_admitted=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
        r['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='run' and a.artifact is None:p.error('run requires an artifact')
    out=prepare() if a.action in ('prepare','campaign') else a.artifact.resolve();print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
