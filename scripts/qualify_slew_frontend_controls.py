#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify reset/disable and phase recovery before selecting physical PFD source."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

import expand_dll_slew_frontends as expansion
import pfd_control_protocol as protocol
import probe_native_pfd_controls as baseline
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='slew_frontend_controls'
sha=expansion.sha
OUTPUTS=expansion.OUTPUTS


def points(worst):
    worst=tuple(worst)
    allowed=set(itertools.product(expansion.coverage.PROCESSES,expansion.coverage.TEMPERATURES))
    if worst not in allowed:raise ValueError('Invalid measured worst source corner')
    result=[(p,t,400) for p,t in sorted(allowed)]
    result += [(p,t,f) for p,t in sorted({('tt',25),('ss',40),worst}) for f in (390,410)]
    return result


def task_plan(report,manifest):
    selected=report['ranked_survivors']
    if not selected:raise ValueError('No source survivor to qualify for controls')
    if len(set(selected))!=len(selected):raise ValueError('Duplicate source survivor')
    indexed={}
    for t in manifest['tasks']:
        s=t['spec'];key=(t['variant'],s['process'],s['temperature'],s['mhz'],s['reference_slew_ps'],s['feedback_slew_ps'],s['offset_ps'])
        if key in indexed:raise ValueError('Duplicated source phase donor')
        indexed[key]=t
    rows={r['task']:r for r in report['results']};result=[]
    for variant in selected:
        candidates=[c for c in report['candidates'] if c['variant']==variant and c['passed']]
        if len(candidates)!=1:raise ValueError('Source survivor lacks a complete measured corner')
        for p,t,f in points(candidates[0]['worst_screened_pvt']):
            for sr,sf in ((100,100),*expansion.coverage.SLEWS):
                keys=[(variant,p,t,f,sr,sf,o) for o in (0,-20,20)]
                if any(key not in indexed for key in keys):raise ValueError('Required source phase/control donor missing')
                donors=[indexed[key] for key in keys]
                area=[rows[d['id']]['result']['phase']['filtered_area_difference_v'] for d in donors[1:]]
                if not area[0]<0<area[1]:raise ValueError('Source donor lacks the required zero bracket')
                result.append(dict(id=donors[0]['id']+'_controls',variant=variant,spec=donors[0]['spec'],
                                   donor=donors[0]['id'],area_limits_v=area))
    return result


def prepared_fixture(parent,task,baseline_manifest):
    donor=next(t for t in json.loads((parent/'manifest.json').read_text())['tasks'] if t['id']==task['donor'])
    deck=(parent/task['donor']/'bench.cir').read_text()
    if sha(parent/task['donor']/'bench.cir')!=donor['deck_sha256']:raise ValueError('Source control donor changed')
    aliases=dict(donor['aliases']);aliases.update({n:n for n in ('REF_FAST','FDB_FAST','RST','ENABLE')})
    # Core/bias/loading must match the independently checked protocol baseline;
    # only the selected source conditioner is appended to this native library.
    model=(parent/(task['variant']+'.spice')).read_text()
    base_model=(ROOT/baseline_manifest['identity']['baseline']/'full.spice').read_text()
    if not model.startswith(base_model):raise ValueError('Source controls changed native PFD/bias/analog loading')
    bm=json.loads((ROOT/baseline_manifest['identity']['baseline']/'manifest.json').read_text())
    gates={n:node for n,node in bm['aliases'].items() if n.startswith(('REF_FF_CLK_','FB_FF_CLK_'))}
    if not gates or set(gates)&set(aliases):raise ValueError('Native receiving-gate observations missing or duplicated')
    aliases.update(gates)
    printed=re.findall(r'(?im)^\.print tran[^\n]+',deck)
    if len(printed)!=1:raise ValueError('Unexpected source control print statement')
    deck=deck.replace(printed[0],printed[0]+' '+' '.join('V('+n+')' for n in gates.values()))
    deck=protocol.apply(deck);ProbeNetwork(model).validate(deck,aliases.values())
    return deck,aliases


def prepare(parent,control_baseline):
    br=baseline.verify(control_baseline)
    if br['baseline_protocol_passed'] is not True:raise ValueError('Complete the passing native control protocol baseline')
    with (parent/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=expansion.verify(parent);pm=expansion.bound(parent);tasks=task_plan(report,pm)
    inputs=dict(pm['identity']['inputs']);bm=baseline.bound(control_baseline)
    inputs.update(bm['identity']['inputs'])
    paths=[parent/n for n in ('manifest.json','summary.json')]+[parent/n for n in pm['libraries']]
    paths += [control_baseline/n for n in ('manifest.json','summary.json',*bm['files'],*OUTPUTS)]
    for t in pm['tasks']:paths += [parent/t['id']/n for n in (*OUTPUTS,'summary.json','bench.cir')]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(pm['identity']['code']);code.update(bm['identity']['code'])
    code[Path(__file__).name]=sha(Path(__file__))
    identity=dict(parent=str(parent.relative_to(ROOT)),baseline=str(control_baseline.relative_to(ROOT)),
                  variants=report['ranked_survivors'],protocol=protocol.VERSION,inputs=inputs,code=code,
                  simulator=provenance(),pdk_source=pm['identity']['pdk_source'],baseline_lef=bm['identity']['lef'],
                  scope='Source-survivor controls: all 15 PVT at 400 MHz, 390/410 MHz at TT25/SS40/measured worst PVT; matched and both extreme slews. Native core/bias/analog loading, observed reset/disable and recovered original phase/clock health. No physical or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);m=dict(identity=identity)
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);prepared=[]
        for t in tasks:
            f=out/t['id'];f.mkdir(exist_ok=True);deck,aliases=prepared_fixture(parent,t,m)
            expansion.write_once(f/'bench.cir',deck)
            prepared.append(dict(t,aliases=aliases,deck_sha256=sha(f/'bench.cir')))
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=prepared,qualified_phy=False,physical_admission=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];parent=ROOT/i['parent']
    if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
        out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
        i['protocol']!=protocol.VERSION or i['simulator']!=provenance() or m['qualified_phy'] is not False or m['physical_admission'] is not False or
        any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
        sha(Path(i['pdk_source']['path']))!=i['pdk_source']['sha256'] or
        sha(Path(i['baseline_lef']['path']))!=i['baseline_lef']['sha256']):raise ValueError('Source control qualification context changed')
    expected=task_plan(json.loads((parent/'summary.json').read_text()),json.loads((parent/'manifest.json').read_text()))
    if [{k:v for k,v in t.items() if k not in ('aliases','deck_sha256')} for t in m['tasks']]!=expected:raise ValueError('Source control coverage changed')
    for t in m['tasks']:
        deck,aliases=prepared_fixture(parent,t,m)
        if sha(out/t['id']/'bench.cir')!=t['deck_sha256'] or deck!=(out/t['id']/'bench.cir').read_text() or aliases!=t['aliases']:
            raise ValueError('Source control fixture or observations changed')
    return m


def measure(folder,task):
    original=expansion.screen.measure(folder,task)
    wave,header=expansion.screen.cal.old.completed(folder)
    for alias,node in task['aliases'].items():header['V('+alias+')']=header['V('+node.upper()+')']
    gates=[n for n in task['aliases'] if n.startswith(('REF_FF_CLK_','FB_FF_CLK_'))]
    control=protocol.measure(wave,header,task['spec']['mhz'],('REF','FDB','REF_FAST','FDB_FAST',*gates))
    signals={n:baseline.phase.original.measurement.column(wave,header,n) for n in ('REF','FDB',*gates)}
    native=baseline.phase.gate_transport(wave[:,1],signals)
    area=original['phase']['filtered_area_difference_v'];lo,hi=task['area_limits_v']
    recovery=bool(lo<=area<=hi)
    return dict(passed=bool(original['passed'] and control['passed'] and native['passed'] and recovery),phase=original,controls=control,native_gate_transport=native,
                recovered_area_within_source_twenty_ps_bracket=recovery)


def aggregate(m,rows):
    expected={t['id']:t for t in m['tasks']}
    if (len(rows)!=len(expected) or len({r['task'] for r in rows})!=len(rows) or
        any(r['task'] not in expected or r['variant']!=expected[r['task']]['variant'] or r['spec']!=expected[r['task']]['spec'] for r in rows)):
        raise ValueError('Source control results missing, duplicated or unexpected')
    candidates=[]
    for variant in m['identity']['variants']:
        subset=[r for r in rows if r['variant']==variant]
        passed=bool(subset and all(r['error'] is None and r['result'] and r['result']['passed'] for r in subset))
        candidates.append(dict(variant=variant,passed=passed,required=sum(t['variant']==variant for t in m['tasks']),passed_cases=sum(bool(r['error'] is None and r['result'] and r['result']['passed']) for r in subset)))
    return dict(source_controls_passed=any(c['passed'] for c in candidates),candidates=candidates,
                ranked_survivors=[c['variant'] for c in candidates if c['passed']],results=rows,qualified_phy=False,physical_admission=False)


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json');parent=ROOT/m['identity']['parent']
    def unchanged(t):
        if (sha(out/'manifest.json')!=stamp or sha(out/t['id']/'bench.cir')!=t['deck_sha256'] or
            sha(parent/(t['variant']+'.spice'))!=m['identity']['inputs'][str((parent/(t['variant']+'.spice')).relative_to(ROOT))] or
            any(sha(ROOT/'scripts'/n)!=h for n,h in m['identity']['code'].items())):raise ValueError('Source control execution context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in (*OUTPUTS,'summary.json')):
            raise ValueError('Partial source control output retained; no retry')
        atomic(out/'state.json',dict(status='qualifying_source_controls',qualified_phy=False))
        def execute(t):
            f=out/t['id'];result=error=None
            try:
                with lease(ROOT,priority=2,label='slew_controls_'+t['id']):
                    unchanged(t);p=subprocess.run(command(f/'ngspice.log',f/'bench.cir'),cwd=f,capture_output=True,text=True)
                (f/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();unchanged(t);result=measure(f,t);unchanged(t)
            except Exception as e:error=str(e)
            row=dict(task=t['id'],variant=t['variant'],spec=t['spec'],result=result,error=error,manifest_sha256=stamp,
                     files={n:sha(f/n) for n in OUTPUTS if (f/n).exists()})
            capture_manifest(f/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        if sha(out/'manifest.json')!=stamp:raise ValueError('Source control manifest changed')
        report=dict(aggregate(m,rows),manifest_sha256=stamp);capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='source_controls_verified' if report['source_controls_passed'] else 'held_source_controls_failed',qualified_phy=False))
    return report


def verify(out):
    m=bound(out);stamp=sha(out/'manifest.json');rows=[]
    for t in m['tasks']:
        f=out/t['id'];r=json.loads((f/'summary.json').read_text())
        if (r['task']!=t['id'] or r['variant']!=t['variant'] or r['spec']!=t['spec'] or r['error'] is not None or
            r['manifest_sha256']!=stamp or set(r['files'])!=set(OUTPUTS) or any(sha(f/n)!=h for n,h in r['files'].items()) or measure(f,t)!=r['result']):
            raise ValueError('Source control result changed')
        rows.append(r)
    report=dict(aggregate(m,rows),manifest_sha256=stamp)
    if report!=json.loads((out/'summary.json').read_text()):raise ValueError('Source control aggregate changed')
    bound(out);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);p.add_argument('--baseline',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if not a.baseline:p.error('--baseline required')
        r=prepare(a.artifact.resolve(),a.baseline.resolve())
    else:r=globals()[a.action](a.artifact.resolve())
    print(r if a.action=='prepare' else json.dumps(r,indent=2),flush=True)
