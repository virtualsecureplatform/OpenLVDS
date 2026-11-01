#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the unclamped receiver with stronger internal restoration after its exact source screens."""
import argparse
import hashlib
import json
from pathlib import Path
import layout_receiver_variant as physical
from receiver_unclamped_restore_experiment import source_variant
from receiver_clamp_experiment import run as recheck

ROOT=Path(__file__).resolve().parents[1]
CASES={'unclamped_captured','clamped_captured','clamped_sharp_control'}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_gate(screen):
    if not screen.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use the isolated tracked-clamp comparison')
    if not (screen/'summary.json').exists() or any(not (screen/name/'summary.json').exists() for name in CASES):
        raise ValueError('Complete all schematic clamp comparisons before layout')
    manifest=json.loads((screen/'manifest.json').read_text())
    if len(manifest['tasks'])!=3 or {t['id'] for t in manifest['tasks']}!=CASES:
        raise ValueError('Incomplete schematic clamp coverage')
    # All three cached summaries exist: recheck cannot launch a missing case.
    recheck(screen)
    summary=json.loads((screen/'summary.json').read_text())
    actual={r['task']:r for r in summary['results']}
    if not summary['diagnostic_complete'] or len(summary['results'])!=3 or set(actual)!=CASES:
        raise ValueError('Incomplete schematic clamp results')
    if any(actual[name]['receiver_transport']['missing_output_edges'] or
           not actual[name]['receiver_transport']['pulses'] or
           any(p['output_edges_in_next_input_period']!=1 for p in actual[name]['receiver_transport']['pulses']) for name in CASES):
        raise ValueError('Stronger-restoration comparison loses or repeats clock edges')
    source=(ROOT/'analog/openlvds.spice').read_text()
    for name in CASES:
        expected=source_variant(source,name.startswith('clamped_'))
        if (screen/name/'candidate.spice').read_text()!=expected:
            raise ValueError('Schematic screen characterizes another receiver source')
    files=[screen/'manifest.json',screen/'summary.json']
    for task in manifest['tasks']:
        folder=screen/task['id']
        files += [folder/n for n in ['candidate.spice','library.spice','bench.cir','summary.json','bench.cir.prn']]
    return {str(p.relative_to(ROOT)):digest(p) for p in files}


def place_monitor(devices):
    moved=[d for d in devices if '__XTRACK__' in d['name']]
    rest=[d for d in devices if d not in moved]
    first=next((i for i,d in enumerate(rest) if '__XIB0__' in d['name']),None)
    if len(moved)!=6 or first is None:raise ValueError('Unexpected unloaded monitor or restoration topology')
    return rest[:first]+moved+rest[first:]


def build(screen):
    proofs=source_gate(screen)
    source=source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    # Move only the six unloaded monitor devices. Existing device banks keep
    # their relative order, matching the preceding physical placement policy.
    original=physical.draw_macro
    def draw(out,top,ports,devices,library):
        return original(out,top,ports,place_monitor(devices),library)
    try:
        physical.draw_macro=draw
        out,summary=physical.build(source,dict(input_tail_scale=2,decision_scale=1,decision_clamped=False,clamp_variant='unclamped_fast_restore',clamp_reference=None,replica_monitor_unloaded=True,reference_widths_um=[32,16],parallel_clamp_units=0,
            restoration_widths_um=[[8,4],[16,8],[16,8]],restoration='Three inverters: P/N widths 8/4, 16/8, 16/8; unchanged final drive and overall polarity',
            placement='Only six unloaded monitor devices moved before first restoration inverter',
            source_screen=str(screen.relative_to(ROOT)),source_screen_proofs=proofs),
            [Path(__file__).name,'receiver_unclamped_restore_experiment.py','receiver_fast_restore_experiment.py','receiver_vref_clamp_experiment.py','receiver_light_clamp_experiment.py','receiver_light_decision_experiment.py','receiver_strong_clamp_experiment.py','receiver_clamp_experiment.py','layout_receiver_gain_candidate.py','layout_receiver_tail_candidate.py'])
    finally:
        physical.draw_macro=original
    print(json.dumps(dict(output=str(out),passed=summary['passed'])),flush=True)
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('screen',type=Path);a=p.parse_args();raise SystemExit(build(a.screen.resolve()))
