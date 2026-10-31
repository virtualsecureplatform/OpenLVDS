#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reanalyze failed RX endpoint traces without changing aperture pass criteria."""
import argparse
from collections import Counter
import json
from pathlib import Path

import characterize_rx_aperture as capture
from rx_aperture_evidence import sha, verify_witness

ROOT=Path(__file__).resolve().parents[1]


def diagnose(root):
    root=root.resolve()
    if not root.is_relative_to(ROOT/'build/characterization/rx_aperture'):
        raise ValueError('Use a captured RX aperture artifact')
    manifest=json.loads((root/'manifest.json').read_text())
    capture.validate(root,manifest)
    table=json.loads((root/'table.json').read_text())
    if (table['manifest_sha256']!=sha(root/'manifest.json') or table['passed'] or
            json.loads((root/'state.json').read_text())['status']!='complete'):
        raise ValueError('Require an unchanged, completed failing campaign')
    expected={capture.condition_id(s):s for s in manifest['conditions']}
    if len(table['results'])!=len(expected) or {capture.condition_id(r['spec']) for r in table['results']}!=set(expected):
        raise ValueError('Incomplete or duplicated aperture results')
    results=[];groups=Counter()
    for result in table['results']:
        if result['passed']:continue
        spec=result['spec'];name=capture.condition_id(spec)
        if spec!=expected[name] or result.get('error')!='Aperture boundary is not bracketed':
            raise ValueError('Unexpected failed fixture: '+name)
        endpoints=[]
        for distance in manifest['identity']['bracket_ps']:
            folder=root/name/('point_'+f'{distance:.6f}'.replace('-','m').replace('.','p'))
            record=json.loads((folder/'summary.json').read_text())
            verify_witness(root,manifest,spec,distance,record['measurement']['passed'])
            endpoints.append(dict(distance_ps=distance,measurement=record['measurement'],
                record_sha256=sha(folder/'summary.json'),waveform_sha256=record['waveform_sha256']))
        groups[f"{spec['process']}/{spec['temperature']}C/clock_{spec['clock_slew_ps']}ps"]+=1
        results.append(dict(condition=name,spec=spec,endpoints=endpoints))
    capture.validate(root,manifest)
    identity=dict(table_sha256=sha(root/'table.json'),manifest_sha256=sha(root/'manifest.json'),
        producer_sha256=sha(Path(__file__)),witness_checker_sha256=sha(ROOT/'scripts/rx_aperture_evidence.py'))
    report=dict(diagnostic=True,qualified_phy=False,identity=identity,conditions=len(expected),
        failed_conditions=len(results),failure_groups=dict(sorted(groups.items())),
        both_endpoints_fail=sum(all(not e['measurement']['passed'] for e in r['endpoints']) for r in results),
        positive_endpoint_valid_but_illegal=sum(r['endpoints'][1]['measurement']['valid'] and
            not r['endpoints'][1]['measurement']['legal'] for r in results),results=results)
    out=ROOT/'build/diagnostics/rx_aperture_failure'/capture.sha(json.dumps(identity,sort_keys=True).encode())[:16]
    out.mkdir(parents=True,exist_ok=True)
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    capture.atomic(out/'summary.json',report)
    print(out/'summary.json',flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path)
    diagnose(parser.parse_args().campaign)
