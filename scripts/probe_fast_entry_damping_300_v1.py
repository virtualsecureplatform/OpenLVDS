#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh native factorial repair pilot, retaining every unmodified control."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import fast_entry_damping_fixture_300_v1 as wiring
import fast_entry_damping_measure_300_v1 as metrology
import probe_tg2_entry_domain_300_v1 as entry
import replay_tg2_loaded_native_300_v2 as entry_replay
from replay_bank_300_v2 import same
from spice_dispatch import lease

ROOT=entry.ROOT
PARENT=ROOT/'build/diagnostics/tg2_entry_domain_pilot_300_v1/b98f2003774d19d6'
PROOF=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v2/22f07da7ba55bc1c'
SLOW_PROOF=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v2/0c774319d495dae9'
VERSION='native-fast-entry-damping-factorial-pilot-300-v1'
CONTEXT='fast_entry_damping_pilot_300_v1'
# Check both physical margins for the combined repair before isolating factors.
SETTINGS=(('combined','2'),('combined','0'),('coarse_shunt','2'),('decode_drive2','2'),('coarse_shunt','0'),('decode_drive2','0'))
sha=entry.sha
atomic=entry.atomic


def evidence():
    m=entry.bound(PARENT,full=False)
    inputs={}
    for proof,number,passed in ((PROOF,'2',False),(SLOW_PROOF,'0',True)):
        pm=json.loads((proof/'manifest.json').read_text());i=pm['identity']
        summary=json.loads((proof/'summary.json').read_text());row=json.loads((PARENT/number/'summary.json').read_text())
        if (proof.parent!=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v2'
                or i['version']!=entry_replay.VERSION or i['parent']!=str(PARENT.relative_to(ROOT)) or i['cases']!=[number]
                or proof.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
                or json.loads((proof/'state.json').read_text())!=dict(status='complete',cases=1,qualified_phy=False)
                or summary['all_selected_loaded_native_metrics_reproduced'] is not True
                or summary['parameters_changed'] is not False or summary['qualified_phy'] is not False
                or summary['whole_bank_admitted'] is not False or len(summary['rows'])!=1
                or summary['rows'][0]['source_point_passed'] is not passed
                or summary['rows'][0]['independent_two_bank_metrics_reproduced'] is not True
                or summary['rows'][0]['all_original_metrics_reproduced'] is not True
                or summary['rows'][0]['task']!=m['tasks'][int(number)]
                or row['task']!=m['tasks'][int(number)] or row['error'] is not None
                or row['result']['two_bank_zero_pilot_passed'] is not passed):
            raise ValueError('Require exact independently reproduced fast-failing and slow-passing entry points')
        for n,h in i['inputs'].items():
            if n in inputs and inputs[n]!=h:raise ValueError('Conflicting entry witness provenance')
            inputs[n]=h
        for name,h in row['files'].items():
            if Path(name).name!=name or i['inputs'].get(str((PARENT/number/name).relative_to(ROOT)))!=h:
                raise ValueError('Original entry witness is not independently bound')
        for path in [*[proof/n for n in ('manifest.json','summary.json','state.json')],PARENT/number/'summary.json']:
            inputs[str(path.relative_to(ROOT))]=sha(path)
    failed=json.loads((PARENT/'2/summary.json').read_text())['result']['banks']['first']
    if (failed['timing']['stage_transport_passed'] is not True or failed['terminal_screen_passed'] is not False
            or failed['control_settling_passed'] is not False):
        raise ValueError('Original fast-entry failure classification changed')
    for n,h in inputs.items():
        if sha(ROOT/n)!=h:raise ValueError('Native entry reference changed')

    return m,inputs


def tasks(out):
    library=(PARENT/'bank.spice').read_text()
    for centered in (True,False):
        for k,(kind,source) in enumerate(SETTINGS):
            folder=PARENT/source;row=json.loads((folder/'summary.json').read_text())
            original=(folder/'bench.cir').read_text();obs=json.loads((folder/'observations.json').read_text())
            include=out/kind/'bank.spice'
            text,bank,observations,revision=wiring.fixture(original,library,obs,kind,include)
            card=entry.SOURCE.numerical_trial.CARD
            if text.count(card+'\n')!=1:raise ValueError('Original VDD-current centering changed')
            if not centered:text=text.replace(card+'\n','',1)
            spec=dict(row['task']['spec'],fast_entry_intervention=kind)
            yield dict(id=str(k+(0 if centered else 6)),kind=kind,source_case=source,centered=centered,spec=spec),text,bank,observations,revision


def prepare():
    _,inputs=evidence()
    # Recheck complete physical/native/math binding of the reused shunt unit.
    _,paths,_=wiring.architecture.source.materials()
    paths+=[PARENT/'manifest.json',PARENT/'bank.spice',ROOT/'clocking_300mhz.json']
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**inputs,**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,inputs=inputs,guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},
        max_workers=1,priority=2,vdd_current_card=entry.SOURCE.numerical_trial.CARD,
        bench_currents_dc_a=0,external_bench_power_excluded=True,source_coverage_qualified=False,
        common_wire_rc_qualified=False,qualified_phy=False,
        scope='Three same-component repair variants, both entry extremes, fresh unmodified controls; no code/PVT, common RC or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);records=[];libraries={}
    for task,text,bank,obs,revision in tasks(out):
        variant=out/task['kind'];variant.mkdir(exist_ok=True);path=variant/'bank.spice'
        if path.exists() and path.read_text()!=bank:raise ValueError('Variant library differs between source conditions')
        if not path.exists():path.write_text(bank)
        libraries[task['kind']]=sha(path)
        folder=out/task['id'];folder.mkdir();(folder/'bench.cir').write_text(text);atomic(folder/'observations.json',obs)
        records.append(dict(task,revision=revision,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    atomic(out/'manifest.json',dict(identity=identity,tasks=records,libraries=libraries,qualified_phy=False))
    bound(out);return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or (i['max_workers'],i['priority'])!=(1,2) or i['vdd_current_card']!=entry.SOURCE.numerical_trial.CARD
            or i['bench_currents_dc_a']!=0 or i['external_bench_power_excluded'] is not True
            or any(i[k] is not False for k in ('source_coverage_qualified','common_wire_rc_qualified','qualified_phy'))
            or m['qualified_phy'] is not False
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}):
        raise ValueError('Fast-entry intervention identity changed')
    if any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items()):
        raise ValueError('Captured fast-entry intervention witness changed')
    libraries={};records=[]
    for task,text,bank,obs,revision in tasks(out):
        path=out/task['kind']/'bank.spice';folder=out/task['id']
        if (path.read_text()!=bank or (folder/'bench.cir').read_text()!=text
                or json.loads((folder/'observations.json').read_text())!=obs):
            raise ValueError('Exact native intervention fixture changed')
        libraries[task['kind']]=sha(path)
        records.append(dict(task,revision=revision,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    if m['tasks']!=records or m['libraries']!=libraries:raise ValueError('Intervention coverage or libraries changed')
    return m


def numerical_pair(out,rows,a,b):
    pair=entry.previous.numerical_pair(out,rows,a,b)
    if rows[a]['error'] is not None or rows[b]['error'] is not None:return pair
    from probe_input_current_origin_300_v1 import booleans
    preserved=booleans(rows[a]['result'])==booleans(rows[b]['result'])
    return dict(pair,passed=bool(pair['passed'] and preserved),all_added_gate_classifications_preserved=preserved)


def verdicts(rows,pairs):
    expected=[(str(k+(0 if centered else 6)),kind,source,centered)
              for centered in (True,False) for k,(kind,source) in enumerate(SETTINGS)]
    if [(r['task']['id'],r['task']['kind'],r['task']['source_case'],r['task']['centered']) for r in rows]!=expected or set(pairs)!={str(k) for k in range(6)}:
        raise ValueError('Require all twelve fresh cases and six complete numerical pairs')
    return {kind:bool(all(rows[j]['error'] is None and rows[j]['result']['two_bank_zero_pilot_passed'] is True
                    for k,(name,_) in enumerate(SETTINGS) if name==kind for j in (k,k+6))
                    and all(pairs[str(k)]['passed'] is True for k,(name,_) in enumerate(SETTINGS) if name==kind))
            for kind in wiring.architecture.KINDS}


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial intervention experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=independent=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                obs=json.loads((folder/'observations.json').read_text())
                result=metrology.measure(folder,obs,task['spec'])
                independent=metrology.measure(folder,obs,task['spec'],independent_reader=True)
                if not same(result,independent):raise ValueError('Independent complete intervention metrics do not reproduce')
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,independent_result=independent,
                     files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        pairs={str(k):numerical_pair(out,rows,k+6,k) for k in range(6)}
        outcomes=verdicts(rows,pairs);bound(out)
        atomic(out/'summary.json',dict(rows=rows,active_numerical_controls=pairs,variant_pilot_passed=outcomes,
            source_coverage_qualified=False,common_wire_rc_qualified=False,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=12,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply captured intervention artifact')
        print(run(a.artifact.resolve()),flush=True)
