#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe every falling-pulse restoration window in completed native RX replays."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from diagnose_link_clock import pulse_transport
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from simulate_link import edge_times

ROOT = Path(__file__).resolve().parents[1]
CODE = ['diagnose_receiver_restoration.py', 'diagnose_link_clock.py',
        'dll_measurements.py', 'simulate_link.py', 'receiver_static_diagnosis.py']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def falling_windows(t, differential, nodes, transport):
    """Use complete falling-to-falling input periods, including response delay.

    CO maxima and RESTORE0 minima describe observed swing, not an inverter's
    static trip voltage. Both restoration transitions and output transport are
    measured separately so a late-stage failure cannot be labelled first-stage.
    """
    falls = edge_times(t, differential, 0, False)
    transitions = edge_times(t, nodes['RESTORE0'], .9, False)
    rows = []
    for pulse in transport['pulses']:
        if pulse['polarity'] != 'falling':
            continue
        at = pulse['input_edge_ns']*1e-9
        future = falls[falls > at+1e-15]
        if not len(future):
            raise ValueError('No complete falling-to-falling observation window')
        end = float(future[0]); keep = (t >= at) & (t < end)
        if not np.any(keep):
            raise ValueError('Empty restoration observation window')
        crossings = transitions[(transitions > at) & (transitions < end)]
        rows.append(dict(pulse, response_window_end_ns=end*1e9,
            co_peak_v=float(nodes['CO'][keep].max()),
            restore0_min_v=float(nodes['RESTORE0'][keep].min()),
            restore1_peak_v=float(nodes['RESTORE1'][keep].max()),
            output_min_v=float(nodes['RXCLOCK'][keep].min()),
            first_restorer_falling_crossings=len(crossings),
            first_restorer_first_latency_ps=float((crossings[0]-at)*1e12) if len(crossings) else None))
    return rows


def diagnose(replay):
    if not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):
        raise ValueError('Use a completed isolated native receiver replay')
    required = ['manifest.json', 'summary.json', 'library.spice']
    required += [case+'/'+name for case in ['captured', 'sharp_control']
                 for name in ['summary.json', 'bench.cir', 'bench.cir.prn']]
    if any(not (replay/n).is_file() for n in required):
        raise ValueError('Complete both full native controls before restoration observation')
    manifest = json.loads((replay/'manifest.json').read_text())
    report = json.loads((replay/'summary.json').read_text()); identity = manifest['identity']
    if (report.get('diagnostic_complete') is not True or
            report.get('manifest_sha256') != sha(replay/'manifest.json') or
            len(manifest['tasks']) != 2 or {t['id'] for t in manifest['tasks']} != {'captured', 'sharp_control'} or
            sha(replay/'library.spice') != manifest['library_sha256']):
        raise ValueError('Incomplete or changed native replay manifest/library')
    proofs = {str((replay/n).relative_to(ROOT)): sha(replay/n) for n in required}
    proofs.update(identity['inputs'])
    proofs.update({'scripts/'+n: h for n,h in identity['code'].items()})
    proofs.update({'scripts/'+n: sha(ROOT/'scripts'/n) for n in CODE})
    def unchanged():
        if any(sha(ROOT/n) != h for n,h in proofs.items()):
            raise ValueError('Native restoration observation evidence changed')
    unchanged(); results = []
    for task in manifest['tasks']:
        case = task['id']; folder = replay/case
        saved = json.loads((folder/'summary.json').read_text())
        if (saved.get('manifest_sha256') != sha(replay/'manifest.json') or
                saved.get('waveform_sha256') != sha(folder/'bench.cir.prn') or
                saved.get('deck_sha256') != task['deck_sha256'] or sha(folder/'bench.cir') != task['deck_sha256'] or
                saved not in report.get('results', [])):
            raise ValueError('Native child trace/report binding changed')
        wave, headers = read_wave(folder/'bench.cir.prn'); t = wave[:,1]
        if (len(t) < 2 or not np.isfinite(wave).all() or np.any(np.diff(t) <= 0) or
                t[0] > 1e-15 or t[-1] < 80e-9-1e-12):
            raise ValueError('Require the full original finite 80 ns native trace')
        column = lambda node: wave[:,headers['V('+node.upper()+')']]
        differential = column('RCP')-column('RCN'); output = column('RXCLOCK')
        transport = pulse_transport(t, differential, output, 15e-9, 75e-9)
        if transport != saved['receiver_transport']:
            raise ValueError('Native transport remeasurement differs from completed report')
        nodes = {name: column(identity['observation_nodes'][name]) for name in ['CO', 'RESTORE0', 'RESTORE1']}
        nodes['RXCLOCK'] = output
        windows = falling_windows(t, differential, nodes, transport)
        missing = [r for r in windows if r['output_edges_in_next_input_period'] == 0]
        results.append(dict(case=case, receiver_transport=transport, falling_windows=windows,
            missing_falling_windows=len(missing),
            missing_without_first_restorer_falling_crossing=sum(r['first_restorer_falling_crossings'] == 0 for r in missing),
            missing_co_peak_range_v=[min(r['co_peak_v'] for r in missing), max(r['co_peak_v'] for r in missing)] if missing else None,
            missing_restore0_min_range_v=[min(r['restore0_min_v'] for r in missing), max(r['restore0_min_v'] for r in missing)] if missing else None))
    unchanged()
    evidence = dict(replay=str(replay.relative_to(ROOT)), files=proofs)
    out = replay/'restoration_observations'/hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out/'summary.json', dict(identity=evidence, qualified_phy=False, qualification_verdict=None,
        original_native_clock_passed=report.get('native_clock_passed') is True, results=results,
        scope='Completed original native 80 ns controls; exact 15–75 ns transport remeasurement and falling-to-falling response windows. Internal buses are wire observations. Swing and 0.9 V crossings do not measure static inverter trip or MOS saturation. No source, physical, admission, numerical-policy or active-pointer change.'))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('replay', type=Path); args = parser.parse_args()
    print(diagnose(args.replay.resolve())/'summary.json', flush=True)
