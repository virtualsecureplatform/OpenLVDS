#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Place the native regular regenerator pair while its timing pilot runs."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import klayout.db as db
import prepare_isolated_fine_placement_v238 as previous
import analyze_isolated_fine_junctions_v246 as corrected
import regular_regenerated_bank_physical_v273 as design

ROOT=previous.ROOT
sha=previous.sha
VERSION='regular-pair-native-bank-graph-and-real-master-placement-v272.1'
CONTEXT='regular_regenerated_placement_v272'
BASE=ROOT/'build/diagnostics/isolated_fine_placement_v238/da8cd048ac28c378'
REFERENCE=ROOT/'build/diagnostics/isolated_fine_bank_junctions_v246/100682d1c98a6745'
PILOT=ROOT/'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
SCOPE='Regular P20/N16 regenerator-pair native graph and actual-master placement/fixed-bus feasibility only; no routing, bank LVS, shared RC, timing selection, clock chain or PHY admission'


def inputs():
    pi,pr=previous.checked(BASE,previous,'placement_feasibility_passed')
    ri,rpi=corrected.bound(REFERENCE);rr=json.loads((REFERENCE/'summary.json').read_text())
    if (ri['parent']!=str(BASE.relative_to(ROOT)) or rpi!=pi
        or json.loads((REFERENCE/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or rr.get('analysis_completed') is not True or any(sha(REFERENCE/n)!=h for n,h in rr['files'].items())):
        raise ValueError('Require unchanged completed corrected native reference for this placement')
    pm=json.loads((PILOT/'manifest.json').read_text());ci=pm['identity'];component=PILOT/'bank.spice'
    if (ci['version']!='qualified-regular-p20n16-pair-output-regeneration-native-pilot-v263.1'
        or PILOT.name!=hashlib.sha256(json.dumps(ci,sort_keys=True).encode()).hexdigest()[:16]
        or sha(component)!=pm['bank_sha256'] or len(ci['observations']['devices'])!=1529):
        raise ValueError('Require exact immutable native regular-pair pilot library')
    # Consume the immutable DUT definition, not live timing rows or state.
    g=design.graph(pi['graph']);plan=design.placement(pi['plan'],g,pi['records'])
    reference=design.reference(g,(REFERENCE/'reference.spice').read_text())
    proof=design.compare_component(g,component.read_text());proof.update(design.inventory_proof(g,reference,component.read_text()))
    proof['all_used_reference_definition_orders_match_named_graph_pins']=True
    paths=[PILOT/'manifest.json',component]
    for parent,i,r in ((BASE,pi,pr),(REFERENCE,ri,rr)):
        paths += [parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]
        paths += [ROOT/n for n in {**i['inputs'],**i.get('code',{})}]
    return pi,g,plan,reference,proof,paths


def prepare():
    pi,g,plan,reference,proof,paths=inputs()
    code=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(pi,version=VERSION,parent=str(BASE.relative_to(ROOT)),pilot_library=str((PILOT/'bank.spice').relative_to(ROOT)),
        corrected_reference=str((REFERENCE/'reference.spice').relative_to(ROOT)),graph=g,plan=plan,graph_proof=proof,
        reference_sha256=hashlib.sha256(reference.encode()).hexdigest(),inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},
        code={str(p.relative_to(ROOT)):sha(p) for p in code},scope=SCOPE)
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
        or sha(out/'reference.spice')!=i['reference_sha256']):raise ValueError('Regular-pair placement context changed')
    pi=json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity'];g=design.graph(pi['graph'])
    if i['graph']!=g or i['plan']!=design.placement(pi['plan'],g,i['records']):raise ValueError('Regular-pair graph or physical placement cannot regenerate')
    if (out/'reference.spice').read_text()!=design.reference(g,(ROOT/i['corrected_reference']).read_text()):
        raise ValueError('Corrected native reference cannot regenerate')
    return i


def run(out):
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial regular-pair placement')
        (out/'state.json').write_text('{"status":"placing","qualified_phy":false}\n')
        error=None;merged=placed=buses=geometry=None
        try:
            merged=previous.stock.merge(out,i);g=i['graph'];plan=i['plan']
            placed=previous.stock.assembly.opendb(out,dict(i,_parent=str(out.relative_to(ROOT))),g,plan)
            file=previous.stock.assembly.gds(out,out,g,plan)
            buses=design.fixed_bus_audit(file,g,plan,i['records']);geometry=previous.stock.assembly.drc(out,file,g['top'])
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
