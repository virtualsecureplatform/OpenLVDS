#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check separate causal rising/falling clock-delay intervals in a completed diagnosis."""
import argparse
import hashlib
import json
from pathlib import Path

from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]


def intervals(records):
    result = {}
    for edge in ['rising', 'falling']:
        rows = [r for r in records if r['edge'] == edge]
        if not rows:
            raise ValueError('Both original clock polarities are required')
        low = max(rows, key=lambda r: r['minimum_common_clock_delay_ps'])
        high = min(rows, key=lambda r: r['maximum_common_clock_delay_ps'])
        lower = max(0., low['minimum_common_clock_delay_ps']); upper = high['maximum_common_clock_delay_ps']
        result[edge] = dict(causal_interval_ps=[lower, upper], nonempty=lower <= upper,
            midpoint_delay_ps=(lower+upper)/2 if lower <= upper else None,
            interval_half_width_ps=(upper-lower)/2 if lower <= upper else None,
            lower_witness_clock_ns=low['clock_ns'], upper_witness_clock_ns=high['clock_ns'])
    if all(r['nonempty'] for r in result.values()):
        shifted = [(r['clock_ns']*1000+result[r['edge']]['midpoint_delay_ps']) for r in records]
        if any(b <= a for a, b in zip(shifted, shifted[1:])):
            raise ValueError('Independent delay targets change the clock edge order')
    return result


def diagnose(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT/'build/diagnostics'):
        raise ValueError('Use a completed diagnostic report')
    report = json.loads(path.read_text()); sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    for name, stamp in report['files'].items():
        if sha(ROOT/name) != stamp:
            raise ValueError('Original capture/aperture diagnosis evidence changed')
    result = dict(qualified_phy=False, inputs={str(path.relative_to(ROOT)): sha(path),
        str(Path(__file__).relative_to(ROOT)): sha(Path(__file__))},
        source_inside_aperture_slew_domain=report['inside_aperture_slew_domain'],
        common_clock_delay_interval_ps=report['same_capture_assignment_clock_shift_interval_ps'],
        independent_edge_delay_intervals=intervals(report['records']),
        scope='Conditional algebra on the original diagnostic endpoint envelopes and fixed capture assignment. '
            'Separate causal edge delays may require duty shaping; no clock shaper or phase circuit is implemented or qualified here. '
            'The original out-of-domain slew, incomplete PVT table, waveform/load feedback and publication-path limitations remain. '
            'New analog architectures must be measured before applying these old-trace numbers.')
    out = path.parent/'independent_edge_budget'; out.mkdir(exist_ok=True)
    capture_manifest(out/'summary.json', result)
    return out, result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('report', type=Path); a = p.parse_args()
    out, result = diagnose(a.report); print(out/'summary.json', flush=True); print(json.dumps(result, indent=2))
