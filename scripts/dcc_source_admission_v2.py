#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate the exact DCC source receipt under the scientific interpreter."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import expand_dcc_clock_hold_v2 as source
import verify_dcc_clock_hold_pvt_v2 as consumer

ROOT=Path(__file__).resolve().parents[1]
sha=source.base.sha


def source_admission(parent):
    m=source.bound(parent)
    identity=dict(artifact=str(parent.relative_to(ROOT)),manifest_sha256=sha(parent/'manifest.json'),
        summary_sha256=sha(parent/'summary.json'),consumer_sha256=sha(Path(consumer.__file__)))
    receipt=ROOT/'build/diagnostics/dcc_clock_hold_pvt_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]/'summary.json'
    report=json.loads(receipt.read_text())
    if (report['artifact']!=identity['artifact'] or report['consumer_sha256']!=identity['consumer_sha256']
        or report['cases']!=270 or report['numerical_errors']!=0 or report['source_only'] is not True
        or report['qualified_phy'] is not False or len(report['candidates'])!=1):
        raise ValueError('Incomplete independent DCC source proof')
    candidate=report['candidates'][0]
    if (candidate['topology']!=[1,'clock_hold','inv_4'] or candidate['cases']!=270 or candidate['pvt_count']!=15
        or candidate['source_screen_passed'] is not True):raise ValueError('DCC candidate failed source qualification')
    rows=json.loads((parent/'summary.json').read_text())['rows']
    if len(m['tasks'])!=270 or [r['task'] for r in rows]!=m['tasks']:
        raise ValueError('DCC source case coverage changed')
    expected=set(itertools.product(['tt','ff','ss','fs','sf'],[0,25,40],[390,400,410],[20,250],[0,-140,140]))
    actual=set()
    required={str((parent/n).relative_to(ROOT)) for n in ['manifest.json','summary.json','state.json']}
    for row in rows:
        spec=row['task']['spec'];actual.add(tuple(spec[k] for k in ['process','temperature','mhz','slew_ps','phase_error_ps']))
        if (spec['drive']!=1 or spec['buffers']!=0 or spec['output_cell']!='inv_4'
            or spec['reset_drive']!=1 or row['error'] is not None or not row['result']['event_integrity_passed']
            or not row['result']['pulse_generator_integrity_passed']
            or (spec['phase_error_ps']==0 and row['result']['symmetric_timing_passed'] is not True)):
            raise ValueError('DCC source result no longer passes')
        required.update(str((parent/row['task']['id']/n).relative_to(ROOT)) for n in consumer.reader.REQUIRED|{'summary.json'})
    if actual!=expected or not required<=set(report['witness_files']):
        raise ValueError('Incomplete DCC source witness coverage')
    if any(sha(ROOT/n)!=v for n,v in report['witness_files'].items()):
        raise ValueError('DCC source witnesses changed')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(json.dumps(dict(receipt=str(source_admission(a.artifact.resolve())))),flush=True)
