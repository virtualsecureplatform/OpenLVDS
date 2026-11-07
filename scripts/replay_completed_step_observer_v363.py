#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recheck completed observer parity and analyze its actual ngspice log.

Read-only analysis of the retained v358 experiment, including its original
console-log parsing mistake. Never edits that experiment or starts SPICE.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
from analyze_step_trace_v361 import analyze
from native_binary_raw_v2 import validate

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/'build/reports/step_observer_prefix_diagnostic/20261107T130431Z'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replay():
    manifest = json.loads((PARENT/'manifest.json').read_text())
    report = json.loads((PARENT/'summary.json').read_text())
    if (manifest['stop_ps'] != 200 or manifest['production_runtime_replaced'] is not False
            or manifest['full_bank_qualification'] is not False
            or [r['variant'] for r in report['rows']] != ['off', 'on']):
        raise ValueError('Require original completed quiet-prefix diagnostic scope')
    inputs = dict(manifest['inputs'])
    paths = [Path(__file__), ROOT/'scripts/analyze_step_trace_v361.py',
             ROOT/'scripts/native_binary_raw_v2.py', PARENT/'manifest.json', PARENT/'summary.json']
    reference = ROOT/manifest['source_reference']
    ref_report = json.loads((reference/'summary.json').read_text())
    paths += [reference/'summary.json', reference/'reference_prefix.raw']
    ref_names, ref = validate(reference/'reference_prefix.raw', set(), ref_report['last_copied_ps']*1e-12)
    waves = []
    rows = []
    for stored in report['rows']:
        folder = PARENT/stored['variant']
        row = json.loads((folder/'summary.json').read_text())
        if row != stored or row['error'] is not None or row['result'] is None:
            raise ValueError('Require complete matching original case summary')
        paths.append(folder/'summary.json')
        for name, expected in row['files'].items():
            path = folder/name
            if sha(path) != expected:
                raise ValueError('Completed observer artifact changed: '+str(path))
            paths.append(path)
        names, data = validate(folder/'bench.raw', set(ref_names), 200e-12)
        if names != ref_names or data.shape[1] != ref.shape[1]:
            raise ValueError('Original native vector order/count changed')
        t = data[:, names.index('time')]
        dt = np.diff(t)*1e12
        stats = dict(records=len(t), last_ps=float(t[-1]*1e12), minimum_step_ps=float(dt.min()),
                     median_step_ps=float(np.median(dt)), mean_step_ps=float(dt.mean()),
                     maximum_step_ps=float(dt.max()), steps_below_0_01ps=int(np.count_nonzero(dt < .01)))
        worst = 0.
        node = None
        rt = ref[:, ref_names.index('time')]
        for k, name in enumerate(names):
            if name == 'time':
                continue
            error = float(np.max(np.abs(np.interp(rt, t, data[:, k])-ref[:, k])))
            if error > worst:
                worst, node = error, name
        difference = dict(maximum_error_at_original_samples_v=worst, worst_vector=node,
                          original_sample_count=len(ref), native_vectors_compared=len(names)-1,
                          all_native_prefix_voltages_within_2mv=bool(worst <= .002))
        if stats != row['result']['steps'] or difference != row['result']['reference_difference']:
            raise ValueError('Original all-vector parity/step measurements do not reproduce')
        trace = analyze((folder/'ngspice.log').read_text())
        if stored['variant'] == 'off' and trace['all_logged_counts']:
            raise ValueError('Logging-off control contains observer events')
        if stored['variant'] == 'on' and not trace['all_logged_counts']:
            raise ValueError('Logging-on actual ngspice log is missing observer events')
        rows.append(dict(variant=stored['variant'], steps=stats, reference_difference=difference,
                         trace=trace, original_waveform_metrics_reproduced=True))
        waves.append(data)
    identical = bool(waves[0].shape == waves[1].shape and np.array_equal(*waves))
    if identical is not True or report['logging_on_off_identical_saved_vectors'] is not True:
        raise ValueError('Observer logging altered saved native voltages/time grid')
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    if any(sha(ROOT/name) != expected for name, expected in inputs.items()):
        raise ValueError('Original diagnostic context or replay input changed')
    out = ROOT/'build/reports/completed_step_observer_replay_v363'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True, exist_ok=False)
    result = dict(rows=rows, inputs=inputs, all_original_waveform_metrics_reproduced=True,
                  logging_on_off_identical_saved_vectors=identical, parameters_changed=False,
                  production_runtime_replaced=False, original_root_cause_proven=False,
                  qualified_phy=False, numpy=np.__version__,
                  scope='Completed 200ps quiet-prefix parity and corrected actual-log analysis; cached trouble fields, no bank/PVT/PHY admission')
    (out/'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(out, flush=True)
    return out


if __name__ == '__main__':
    replay()
