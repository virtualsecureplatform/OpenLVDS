#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Four actual native zero-code sections with a fresh unshifted reference."""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_tg2_entry_domain_300_v1 as entry
import four_bank_fixture_300_v1 as wiring
import four_bank_native_measure_300_v1 as metrology
from four_bank_numerical_pair_300_v1 import numerical_pair
from spice_dispatch import lease

ROOT=entry.ROOT
SOURCE=entry.SOURCE
PARENT=entry.SOURCE_BANK
VERSION='double-tg-four-section-native-zero-diagnostic-300-v1'
CONTEXT='tg2_four_section_zero_pilot_300_v1'
sha=entry.sha
atomic=entry.atomic


def fixture(out,identity,library,spec,centered):
    text=SOURCE.fixture(out,identity,dict(variant=SOURCE.VARIANT,spec=spec,centered=centered))
    include=f'.include "{out/SOURCE.VARIANT}/bank.spice"'
    if text.count(include)!=1:raise ValueError('Original source library include changed')
    text=text.replace(include,f'.include "{out}/bank.spice"',1)
    source=deepcopy(identity['source_identity']);source['observations']=deepcopy(identity['observations'][SOURCE.VARIANT])
    text,obs=wiring.fixture(text,library,identity['revisions'][SOURCE.VARIANT]['macro_top'],source)
    if sum(len(o['devices']) for o in obs.values())!=8224:raise ValueError('Four-section native inventory changed')
    return text,obs


def tasks(out,identity,library,spec):
    for k in range(2):
        text,obs=fixture(out,identity,library,spec,k==0)
        yield dict(id=str(k),centered=k==0,spec=spec),text,obs


def prepare(proof):
    baseline,evidence=entry.require_reference(proof)
    source=SOURCE.bound(PARENT,full=False);spec=baseline['identity']['spec']
    library=(PARENT/SOURCE.VARIANT/'bank.spice').read_text()
    paths=[PARENT/'manifest.json',PARENT/SOURCE.VARIANT/'bank.spice',ROOT/'clocking_300mhz.json']
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**evidence,**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),reference_proof=str(proof.relative_to(ROOT)),
        inputs=inputs,guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},spec=spec,
        max_workers=1,priority=2,profile_sha256=sha(ROOT/'clocking_300mhz.json'),
        bench_current_card=SOURCE.numerical_trial.CARD,bench_current_dc_a=0,bench_current_peak_a=.001,
        power_excludes_external_bench_load=True,source_full_bank_coverage_qualified=False,
        source_active_numerical_parity_qualified=False,detector_dcc_fanout_qualified=False,
        common_wire_rc_qualified=False,qualified_phy=False,
        scope='Four-section native zero-code transport diagnostic only; no phase calibration, fanout, routing or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_text(library);records=[]
    for task,text,obs in tasks(out,source['identity'],library,spec):
        folder=out/task['id'];folder.mkdir();(folder/'bench.cir').write_text(text);atomic(folder/'observations.json',obs)
        records.append(dict(task,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    atomic(out/'manifest.json',dict(identity=identity,tasks=records,bank_sha256=sha(out/'bank.spice'),qualified_phy=False))
    bound(out)
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or (i['max_workers'],i['priority'])!=(1,2)
            or i['profile_sha256']!=sha(ROOT/'clocking_300mhz.json')
            or i['bench_current_card']!=SOURCE.numerical_trial.CARD or i['bench_current_dc_a']!=0
            or i['bench_current_peak_a']!=.001 or i['power_excludes_external_bench_load'] is not True
            or any(i[key] is not False for key in ('source_full_bank_coverage_qualified',
                'source_active_numerical_parity_qualified','detector_dcc_fanout_qualified','common_wire_rc_qualified','qualified_phy'))
            or m['qualified_phy'] is not False
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}):
        raise ValueError('Four-section experiment identity changed')
    if any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items()):
        raise ValueError('Captured four-section input changed')
    proof=ROOT/i['reference_proof']
    if (proof.parent!=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v1'
            or any(str((proof/n).relative_to(ROOT)) not in i['guards'] for n in ('manifest.json','summary.json','state.json'))):
        raise ValueError('Four-section reference receipt binding changed')
    source=SOURCE.bound(PARENT,full=False);library=(PARENT/SOURCE.VARIANT/'bank.spice').read_text()
    if i['spec']!=source['tasks'][0]['spec']:raise ValueError('Four-section source specification changed')
    if (out/'bank.spice').read_text()!=library or sha(out/'bank.spice')!=m['bank_sha256']:
        raise ValueError('Four-section native library changed')
    expected=[]
    for task,text,obs in tasks(out,source['identity'],library,i['spec']):
        folder=out/task['id']
        if (folder/'bench.cir').read_text()!=text or json.loads((folder/'observations.json').read_text())!=obs:
            raise ValueError('Four-section wiring or observation maps changed')
        expected.append(dict(task,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    if m['tasks']!=expected:raise ValueError('Four-section fresh reference coverage changed')
    return m


def pilot_passed(rows,pair):
    if (len(rows)!=2 or [(r['task']['id'],r['task']['centered']) for r in rows]!=[('0',True),('1',False)]
            or rows[0]['task']['spec']!=rows[1]['task']['spec']):
        raise ValueError('Require both fresh four-section native cases')
    return bool(pair['passed'] is True and all(r['error'] is None and
        r['result']['four_section_transport_passed'] is True for r in rows))


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial four-section experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=metrology.measure(folder,json.loads((folder/'observations.json').read_text()),task['spec'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        pair=numerical_pair(out,rows,1,0);passed=pilot_passed(rows,pair);bound(out)
        atomic(out/'summary.json',dict(rows=rows,active_numerical_control=pair,four_section_pilot_passed=passed,
            source_full_bank_coverage_qualified=False,source_active_numerical_parity_qualified=False,
            detector_dcc_fanout_qualified=False,common_wire_rc_qualified=False,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=2,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',type=Path)
    a=p.parse_args();target=a.artifact.resolve();print(prepare(target) if a.action=='prepare' else run(target),flush=True)
