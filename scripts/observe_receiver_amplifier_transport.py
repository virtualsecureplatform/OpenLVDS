#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe completed native amplifier stages without changing transport admission."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from diagnose_receiver_restoration import diagnose
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from simulate_link import edge_times

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
STAGES = [('decision', 'decision_difference', 0, True),
          ('amplifier', 'amplifier_reference_difference', 0, True),
          ('restore0', 'RESTORE0', .9, False),
          ('restore1', 'RESTORE1', .9, True),
          ('output', 'RXCLOCK', .9, False)]


def amplifier_column(headers, leaf):
    pattern = r'V\(XRC:OPENLVDS_RECEIVER_CORE__'+re.escape(leaf)+r'(?:\.(?:T|N)\d+)?\)'
    found = [column for name, column in headers.items() if re.fullmatch(pattern, name.upper())]
    if len(found) != 1:
        raise ValueError('Require one explicitly printed native amplifier bus: '+leaf)
    return found[0]


def stage_windows(t, nodes, windows):
    t = np.asarray(t)
    values = dict(nodes, decision_difference=nodes['CO']-nodes['CL'],
        amplifier_reference_difference=nodes['AMP_OUT']-nodes['CO_TRACK'])
    if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0) or any(
            v.shape != t.shape or not np.isfinite(v).all() for v in values.values()):
        raise ValueError('Require finite matching increasing stage observations')
    crossings = {name:edge_times(t, values[node], threshold, rising) for name,node,threshold,rising in STAGES}
    rows = []
    for window in windows:
        start = window['input_edge_ns']*1e-9; end = window['response_window_end_ns']*1e-9
        keep = (t >= start) & (t < end)
        if not end > start or not np.any(keep):
            raise ValueError('Empty amplifier response window')
        stages = {}
        for name,node,threshold,rising in STAGES:
            edges = crossings[name]; edges = edges[(edges > start) & (edges < end)]
            stages[name] = dict(crossing_count=len(edges), threshold_v=threshold, rising=rising,
                latencies_ps=[float((edge-start)*1e12) for edge in edges])
        ranges = {name:dict(min_v=float(v[keep].min()), max_v=float(v[keep].max())) for name,v in values.items()}
        rows.append(dict(window, stages=stages, ranges=ranges))
    return rows


def observe(replay):
    # The existing read-only producer validates both complete original 80 ns
    # controls, original 15–75 ns transport remeasurement and all input/code
    # hashes. Its own result explicitly carries no qualification admission.
    restoration = diagnose(replay)
    report = restoration/'summary.json'
    observed = json.loads(report.read_text())
    proofs = dict(observed['identity']['files'])
    proofs[str(report.relative_to(ROOT))] = sha(report)
    for name in [Path(__file__).name, 'diagnose_receiver_restoration.py', 'dll_measurements.py',
                 'simulate_link.py', 'receiver_static_diagnosis.py']:
        proofs['scripts/'+name] = sha(ROOT/'scripts'/name)
    def unchanged():
        if any(sha(ROOT/n) != h for n,h in proofs.items()):
            raise ValueError('Amplifier observation evidence changed')
    unchanged()
    manifest = json.loads((replay/'manifest.json').read_text())
    mapping = manifest['identity']['observation_nodes']
    results = []
    for case in observed['results']:
        wave, headers = read_wave(replay/case['case']/'bench.cir.prn')
        nodes = {name:wave[:,headers['V('+mapping[name].upper()+')']] for name in ['CO', 'CL', 'CO_TRACK', 'RESTORE0', 'RESTORE1']}
        for name in ['AMP_CT', 'AMP_L', 'AMP_OUT']:
            nodes[name] = wave[:,amplifier_column(headers, name)]
        nodes['RXCLOCK'] = wave[:,headers['V(RXCLOCK)']]
        rows = stage_windows(wave[:,1], nodes, case['falling_windows'])
        missing = [r for r in rows if r['output_edges_in_next_input_period'] == 0]
        results.append(dict(case=case['case'], falling_windows=rows, missing_falling_windows=len(missing),
            missing_without_positive_decision_difference=sum(r['ranges']['decision_difference']['max_v'] <= 0 for r in missing),
            missing_without_positive_amplifier_reference_difference=sum(r['ranges']['amplifier_reference_difference']['max_v'] <= 0 for r in missing),
            missing_without_restore0_crossing=sum(r['stages']['restore0']['crossing_count'] == 0 for r in missing),
            missing_despite_restore0_crossing=sum(r['stages']['restore0']['crossing_count'] > 0 for r in missing)))
    unchanged()
    identity = dict(replay=str(replay.relative_to(ROOT)), files=proofs)
    out = replay/'amplifier_transport_observations'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out/'summary.json', dict(identity=identity, results=results, qualified_phy=False,
        scope='Read-only complete original captured/sharp controls. Full falling-to-falling response periods in the original 15–75 ns transport window. CO-minus-CL and AMP_OUT-minus-loaded-CO_TRACK are printed bus observations, not MOS-terminal gain, static inverter trip, phase margin or causal proof. Restorer/output crossings use 0.9 V only to localize observed transitions. No scientific fixture/model, admission, selected PHY or numerical policy changes.'))
    return out/'summary.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('replay', type=Path); a = p.parse_args()
    print(observe(a.replay.resolve()), flush=True)
