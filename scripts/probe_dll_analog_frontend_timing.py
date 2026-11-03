#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen DC-ready analog frontends on the complete native SS40 phase fixture.

No standard-cell isolation calibration transfers to the changed analog bias
and input circuit. Both known false-BAD cases dispatch first. Full-PVT,
controls, physical, closed-loop and PHY qualification remain required.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import probe_dll_analog_frontend_dc as dc
import pilot_native_slew_dll as pilot
import probe_native_pfd_controls as baseline
from dll_campaign import atomic,bias_reference_count
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command,provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_analog_frontend_timing'
sha=dc.sha
OUTPUTS=pilot.OUTPUTS


def tasks(variants):
    if not variants or len(set(variants))!=len(variants) or any(v not in dc.policy.VARIANTS for v in variants):raise ValueError('Require unique DC-ready bounded analog variants')
    return [dict(id=v+'_'+t['id'],variant=v,spec=t['spec']) for t in pilot.tasks() for v in variants]


def admission(parent,clock_baseline):
    if not parent.is_relative_to(ROOT/'build/diagnostics'/dc.NAMESPACE):raise ValueError('Require the complete analog DC grid')
    if not clock_baseline.is_relative_to(ROOT/'build/diagnostics'/baseline.NAMESPACE):raise ValueError('Require the retained native clock-observation baseline')
    with (parent/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);report=dc.verify(parent);m=dc.bound(parent)
        if not report['dc_ready_variants']:raise ValueError('No analog frontend passed DC headroom/current/level/stress checks')
    br=baseline.verify(clock_baseline);bm=baseline.bound(clock_baseline)
    if (br['baseline_protocol_passed'] is not True or bm['identity']['qualification']!=m['identity']['qualification_reference'] or
        (clock_baseline/'full.spice').read_bytes()!=(ROOT/m['identity']['qualification_reference']/'full.spice').read_bytes()):
        raise ValueError('Clock observations do not belong to the retained native circuit')
    return m,report,bm


def context(identity):
    q=ROOT/identity['qualification_reference'];qm=json.loads((q/'manifest.json').read_text())
    bm=json.loads((ROOT/identity['clock_baseline']/'manifest.json').read_text())
    gates={n:node for n,node in bm['aliases'].items() if n.startswith(('REF_FF_CLK_','FB_FF_CLK_'))}
    if len(gates)!=4:raise ValueError('Require all four actual retained receiving MOS gates')
    text=(q/'slew_ss_40_0ps_20_200/bench.cir').read_text()
    return qm['identity']['full_models']['observation_nodes'],gates,text[:text.index('XB PB NB VDDIO 0 lvds_bias')]


def fixture(task,observations,gates,prefix,library,model):
    deck,aliases=pilot.fixture(task['spec'],observations,gates,prefix,library,model)
    original='XP REF FDB RST VDDD UP DN VDDD 0 lvds_pfd'
    if deck.splitlines().count(original)!=1:raise ValueError('Native eight-port phase fixture changed')
    extra='XF REF FDB REF_FAST FDB_FAST PB VDDIO VDDD 0 '+dc.policy.PAIR
    deck=deck.replace(original,extra+'\n'+original.replace('XP REF FDB','XP REF_FAST FDB_FAST'))
    nodes={'REF_FAST','FDB_FAST','XF:VCM','XF:NTAIL'}|{n for d in dc.policy.circuit(task['variant'])[1] for n in d['terminals'] if n!='0'}
    # Preserve all original aliases and append only actually instantiated nodes.
    nodes-=set(aliases.values())
    extra_aliases={n:n for n in sorted(nodes)}
    if set(extra_aliases)&set(aliases):raise ValueError('Analog timing observation aliases collide')
    aliases.update(extra_aliases)
    printed=re.findall(r'(?im)^\.print tran[^\n]+',deck)
    if len(printed)!=1:raise ValueError('Native phase print statement changed')
    deck=deck.replace(printed[0],printed[0]+' '+' '.join('V('+n+')' for n in extra_aliases.values()))
    ProbeNetwork(model).validate(deck,aliases.values())
    if bias_reference_count(deck,model)!=1:raise ValueError('Analog timing duplicated endpoint bias')
    return deck,aliases


def prepare(parent,clock_baseline):
    pm,report,bm=admission(parent,clock_baseline);pi=pm['identity'];q=ROOT/pi['qualification_reference']
    pending=tasks(report['dc_ready_variants']);inputs=dict(pi['inputs']);inputs.update(bm['identity']['inputs'])
    paths=[parent/n for n in ('manifest.json','summary.json',*pm['libraries'])]
    for t in pm['tasks']:paths += [parent/t['id']/n for n in (*dc.OUTPUTS,'summary.json','bench.cir')]
    paths += [clock_baseline/n for n in ('manifest.json','summary.json',*bm['files'],*baseline.OUTPUTS)]
    paths += [q/'manifest.json',q/'slew_ss_40_0ps_20_200/bench.cir']
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(pi['code']);code.update(bm['identity']['code'])
    for n in (Path(__file__).name,'pilot_native_slew_dll.py','dll_analog_frontend.py','probe_dll_analog_frontend_dc.py','screen_dll_slew_frontends.py'):
        code[n]=sha(ROOT/'scripts'/n)
    identity=dict(parent=str(parent.relative_to(ROOT)),clock_baseline=str(clock_baseline.relative_to(ROOT)),
                  qualification_reference=pi['qualification_reference'],variants=report['dc_ready_variants'],policy=dc.policy.VERSION,
                  inputs=inputs,code=code,pdk=pi['pdk'],lef=bm['identity']['lef'],simulator=provenance(),
                  scope='Source analog frontend, full retained native PFD/bias/analog loading. SS40/400 MHz, both unequal slews, 0 and +/-20/50/150/300 ps. Known failures first, actual receiving gates and all frontend MOS voltage stress. No isolation-bench transfer, physical, all-PVT, loop or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);observations,gates,prefix=context(identity)
    from expand_dll_slew_frontends import write_once
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);libraries={};prepared=[]
        for v in identity['variants']:
            write_once(out/(v+'.spice'),(parent/(v+'.spice')).read_text());libraries[v+'.spice']=sha(out/(v+'.spice'))
        for t in pending:
            folder=out/t['id'];folder.mkdir(exist_ok=True)
            deck,aliases=fixture(t,observations,gates,prefix,out/(t['variant']+'.spice'),(out/(t['variant']+'.spice')).read_text())
            write_once(folder/'bench.cir',deck);prepared.append(dict(t,aliases=aliases,deck_sha256=sha(folder/'bench.cir')))
        (out/'producers').mkdir(exist_ok=True)
        for n in code:write_once(out/'producers'/n,(ROOT/'scripts'/n).read_text())
        capture_manifest(out/'manifest.json',dict(identity=identity,libraries=libraries,tasks=prepared,physical_admission=False,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];parent=ROOT/i['parent']
    if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
        out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or i['simulator']!=provenance() or
        i['policy']!=dc.policy.VERSION or m['physical_admission'] is not False or m['qualified_phy'] is not False or
        any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
        any(sha(ROOT/'scripts'/n)!=h or sha(out/'producers'/n)!=h for n,h in i['code'].items()) or
        sha(Path(i['pdk']['path']))!=i['pdk']['sha256'] or sha(Path(i['lef']['path']))!=i['lef']['sha256'] or
        set(m['libraries'])!={v+'.spice' for v in i['variants']} or any(sha(out/n)!=h or (out/n).read_bytes()!=(parent/n).read_bytes() for n,h in m['libraries'].items()) or
        [{k:v for k,v in t.items() if k not in ('aliases','deck_sha256')} for t in m['tasks']]!=tasks(i['variants'])):
        raise ValueError('Analog timing context changed')
    pm,report,bm=admission(parent,ROOT/i['clock_baseline'])
    if i['variants']!=report['dc_ready_variants'] or i['qualification_reference']!=pm['identity']['qualification_reference']:
        raise ValueError('Analog timing DC admission changed')
    observations,gates,prefix=context(i)
    for t in m['tasks']:
        deck,aliases=fixture(t,observations,gates,prefix,out/(t['variant']+'.spice'),(out/(t['variant']+'.spice')).read_text())
        if deck!=(out/t['id']/'bench.cir').read_text() or aliases!=t['aliases'] or sha(out/t['id']/'bench.cir')!=t['deck_sha256']:
            raise ValueError('Analog timing fixture or observations changed')
    return m


def frontend_health(time,signals,variant):
    stress=[]
    for device in dc.policy.circuit(variant)[1]:
        values=[np.zeros(len(time)) if n=='0' else signals[n] for n in device['terminals']]
        maximum=max(float(np.max(abs(a-b))) for a,b in itertools.combinations(values,2))
        limit=5.5 if device['model']==dc.policy.P5 else 1.95
        stress.append(dict(device=device['name'],max_terminal_difference_v=maximum,limit_v=limit,passed=bool(maximum<=limit)))
    keep=(time>120e-9)&(time<160e-9)
    if not np.any(keep):raise ValueError('Missing original analog timing window')
    common=signals['XF:VCM'][keep];reference=bool(np.max(abs(common-.9))<=.01)
    return dict(passed=bool(reference and all(s['passed'] for s in stress)),common_mode_min_v=float(common.min()),
                common_mode_max_v=float(common.max()),common_mode_ripple_pp_v=float(np.ptp(common)),common_mode_passed=reference,stress=stress)


def measure(folder,task):
    original=pilot.measure(folder,task);wave,header=pilot.original.completed(folder)
    for alias,node in task['aliases'].items():header['V('+alias+')']=header['V('+node.upper()+')']
    signals={n:pilot.original.measurement.column(wave,header,n) for n in task['aliases']}
    integrity=dc.screen.clock_integrity(wave[:,1],signals);health=frontend_health(wave[:,1],signals,task['variant'])
    return dict(passed=bool(original['passed'] and integrity and health['passed']),native_phase=original,
                conditioned_clock_integrity_passed=bool(integrity),frontend_health=health)


def aggregate(m,rows):
    expected={t['id']:t for t in m['tasks']}
    if ([{k:v for k,v in t.items() if k not in ('aliases','deck_sha256')} for t in m['tasks']]!=tasks(m['identity']['variants']) or
        len(rows)!=len(expected) or len({r['task'] for r in rows})!=len(rows) or
        any(r['task'] not in expected or r['variant']!=expected[r['task']]['variant'] or r['spec']!=expected[r['task']]['spec'] for r in rows)):
        raise ValueError('Analog timing results missing, duplicated or unexpected')
    candidates=[]
    for variant in m['identity']['variants']:
        selected=[r for r in rows if r['variant']==variant];checks=[];zeros=[]
        passed=all(r['error'] is None and r['result'] and r['result']['passed'] for r in selected)
        for slew in pilot.coverage.SLEWS:
            group={r['spec']['offset_ps']:r for r in selected if (r['spec']['reference_slew_ps'],r['spec']['feedback_slew_ps'])==slew}
            valid=all(r['error'] is None and r['result'] for r in group.values());monotonic=balance=False;zero=None
            if valid:
                values=[group[o]['result']['native_phase']['phase']['filtered_area_difference_v'] for o in pilot.coverage.SOURCE_OFFSETS]
                monotonic=bool(np.isfinite(values).all() and all(b>a for a,b in zip(values,values[1:])))
                lo=group[-20]['result']['native_phase']['phase']['filtered_area_difference_v'];hi=group[20]['result']['native_phase']['phase']['filtered_area_difference_v']
                balance=bool(lo<0<hi)
                if balance:zero=float(-20+40*(-lo)/(hi-lo));zeros.append(abs(zero))
            passed=passed and monotonic and balance
            checks.append(dict(slew=list(slew),monotonic=monotonic,zero_bracket_passed=balance,estimated_zero_offset_ps=zero))
        powers=[r['result']['native_phase']['mean_power_w'] for r in selected if r['error'] is None and r['result']]
        candidates.append(dict(variant=variant,passed=bool(passed),checks=checks,
            estimated_zero_offset_max_abs_ps=max(zeros) if len(zeros)==2 else None,mean_power_w=float(np.mean(powers)) if powers else None,
            mos_gate_area_um2=sum(d['width_um']*d['length_um'] for d in dc.policy.circuit(variant)[1])))
    eligible=[c for c in candidates if c['passed']];rank=[]
    while eligible:
        best=min(c['estimated_zero_offset_max_abs_ps'] for c in eligible)
        winner=min((c for c in eligible if c['estimated_zero_offset_max_abs_ps']<=best+2),key=lambda c:(c['mean_power_w'],c['mos_gate_area_um2'],c['variant']))
        rank.append(winner['variant']);eligible.remove(winner)
    return dict(analog_source_screen_passed=bool(rank),ranked_survivors=rank,candidates=candidates,results=rows,
                physical_admission=False,qualified_phy=False,scope=m['identity']['scope'])


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    def unchanged(t):
        if (sha(out/'manifest.json')!=stamp or sha(out/t['id']/'bench.cir')!=t['deck_sha256'] or
            sha(out/(t['variant']+'.spice'))!=m['libraries'][t['variant']+'.spice'] or
            any(sha(ROOT/'scripts'/n)!=h for n,h in m['identity']['code'].items())):raise ValueError('Analog timing execution context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in (*OUTPUTS,'summary.json')):raise ValueError('Partial analog timing output retained; no retry')
        atomic(out/'state.json',dict(status='screening_analog_timing',qualified_phy=False))
        def execute(t):
            folder=out/t['id'];result=error=None
            try:
                with lease(ROOT,priority=2,label='dll_analog_timing_'+t['id']):
                    unchanged(t);p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();unchanged(t);result=measure(folder,t);unchanged(t)
            except Exception as e:error=str(e)
            row=dict(task=t['id'],variant=t['variant'],spec=t['spec'],result=result,error=error,manifest_sha256=stamp,
                     files={n:sha(folder/n) for n in OUTPUTS if (folder/n).exists()})
            capture_manifest(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        if sha(out/'manifest.json')!=stamp:raise ValueError('Analog timing manifest changed')
        report=dict(aggregate(m,rows),manifest_sha256=stamp);capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='analog_timing_screened' if report['ranked_survivors'] else 'held_analog_timing_failed',qualified_phy=False))
    return report


def verify(out):
    m=bound(out);stamp=sha(out/'manifest.json');rows=[]
    for t in m['tasks']:
        f=out/t['id'];r=json.loads((f/'summary.json').read_text())
        if (r['task']!=t['id'] or r['variant']!=t['variant'] or r['spec']!=t['spec'] or r['error'] is not None or
            r['manifest_sha256']!=stamp or set(r['files'])!=set(OUTPUTS) or any(sha(f/n)!=h for n,h in r['files'].items()) or measure(f,t)!=r['result']):
            raise ValueError('Analog timing result changed')
        rows.append(r)
    report=dict(aggregate(m,rows),manifest_sha256=stamp)
    if report!=json.loads((out/'summary.json').read_text()):raise ValueError('Analog timing aggregate changed')
    bound(out);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);p.add_argument('--clock-baseline',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if not a.clock_baseline:p.error('--clock-baseline required')
        result=prepare(a.artifact.resolve(),a.clock_baseline.resolve())
    else:result=globals()[a.action](a.artifact.resolve())
    print(result if a.action=='prepare' else json.dumps(result,indent=2),flush=True)
