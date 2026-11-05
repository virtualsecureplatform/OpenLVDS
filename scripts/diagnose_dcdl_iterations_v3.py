#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare terminal ITL4 failures before input or between the two input pulses.

Retained aborted records are numerical diagnostics only. No prefix can satisfy
the complete 20 ns transient, pulse/timing, voltage-safety or PHY gates.
"""
import argparse
import hashlib
import json
import math
from decimal import Decimal
import re
import sys
from pathlib import Path
import diagnose_dcdl_iterations_v2 as previous

ROOT=previous.ROOT
sha=previous.sha
VERSION='matched-dcdl-pre-input-and-inter-pulse-iteration-failure-v2.2'
CONTEXT='dcdl_iteration_failure_v3'


def phase(time):
    if 0<time<2.1e-9:return 'before-first-input-rise'
    if 6.1e-9<time<12.1e-9:return 'after-first-input-fall-before-second-input-rise'
    raise ValueError('Failure is outside the explicitly supported input epochs')


def abort_time_agrees(time,log):
    tokens=re.findall(r'Timestep too small; time = ([\deE.+-]+)',log)
    if len(tokens)!=1:raise ValueError('Require one printed failure time')
    value=Decimal(tokens[0]);resolution=float(Decimal(10)**value.as_tuple().exponent)
    return math.isfinite(time) and abs(time-float(value))<=resolution/2+2*math.ulp(time)


def diagnose(parent,case):
    m,pm=previous.pilot.bound(parent);baseline=ROOT/m['identity']['parent']
    task=next(t for t in m['tasks'] if t['id']==case);original=pm['tasks'][int(case)]
    before=(baseline/case/'bench.cir').read_text();after=(parent/case/'bench.cir').read_text()
    # Regenerate the baseline fixture as well as the title/ITL4-only adapter.
    if (before!=previous.pilot.parent_pilot.fixture(baseline,original['spec'],pm['identity']['devices'])
        or after!=previous.pilot.fixture(before)):raise ValueError('Matched decks differ beyond title and ITL4')
    rows=[];files=[]
    for folder,expected in [(baseline/case,original),(parent/case,task)]:
        r=json.loads((folder/'summary.json').read_text())
        if r['task']!=expected or r['error'] is None or r['result'] is not None:
            raise ValueError('Require two terminal numerical failures of the exact matched case')
        if not {'bench.raw','bench.cir','bench.ngspice.cir','ngspice.log','console.log'}<=set(r['files']):
            raise ValueError('Missing terminal failure witnesses')
        for n,digest in r['files'].items():
            if sha(folder/n)!=digest:raise ValueError('Changed numerical failure evidence')
            files.append(folder/n)
        translated,_=previous.runner.translate((folder/'bench.cir').read_text())
        if translated!=(folder/'bench.ngspice.cir').read_text():raise ValueError('Translated solver deck changed')
        log=(folder/'ngspice.log').read_text();failure=previous.failure(log);raw=previous.prefix(folder/'bench.raw')
        if not abort_time_agrees(raw['last_time_s'],log) or raw['last_time_s']>=20e-9:
            raise ValueError('Terminal numerical abort and incomplete raw prefix do not agree')
        rows.append(dict(folder=str(folder.relative_to(ROOT)),failure=failure,prefix=raw,
                         input_epoch=phase(raw['last_time_s'])))
        files.append(folder/'summary.json')
    files += [parent/'manifest.json',parent/'state.json',parent/'summary.json',baseline/'manifest.json',
              Path(__file__),Path(previous.__file__),Path(previous.pilot.__file__),Path(previous.runner.__file__)]
    files += [ROOT/n for n in m['identity']['inputs']]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),case=case,byteorder=sys.byteorder,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files})
    a,b=rows
    same_payload=all(a['prefix'][k]==b['prefix'][k] for k in ['variables','complete_records','payload_sha256','first_time_s','last_time_s'])
    same_error=all(a['failure'][k]==b['failure'][k] for k in ['reported_time_s','reported_timestep_s','reported_node'])
    result=dict(identity=identity,rows=rows,only_title_and_itl4_changed=True,translated_decks_verified=True,
        partial_payloads_bit_identical=same_payload,reported_failure_identical=same_error,
        iteration_increase_resolved_failure=False,diagnosis_verified=True,completed_transient=False,
        qualified_phy=False,electrical_verdict=None,
        scope='Two terminal numerical failures with incomplete pre-input/inter-pulse records only; no complete pulse/timing, voltage safety, speedup, ROM or PHY admission; reported solver node is not a proven root cause')
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Failure evidence changed during diagnosis')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);previous.pilot.atomic(out/'summary.json',result);return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--case',choices=['0','2'],required=True)
    a=p.parse_args();print(diagnose(a.artifact.resolve(),a.case),flush=True)
