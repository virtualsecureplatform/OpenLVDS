#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the unclamped receiver with LVT first-stage restoration after its exact source screens."""
import argparse
import hashlib
import json
from pathlib import Path
import layout_receiver_variant as physical
from receiver_lvt_restore_experiment import source_variant
from receiver_clamp_experiment import run as recheck
import receiver_lvt_static as dc
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]
CASES={'unclamped_captured','clamped_captured','clamped_sharp_control'}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def static_gate(screen):
    if not screen.is_relative_to(ROOT/'build/diagnostics/receiver_lvt_static'):
        raise ValueError('Use the isolated LVT static screen')
    if not (screen/'summary.json').exists():
        raise ValueError('Complete the LVT static screen before layout')
    dc.run(screen)  # A cached complete case only; never starts a missing run.
    manifest=json.loads((screen/'manifest.json').read_text())
    report=json.loads((screen/'summary.json').read_text())
    metrics=report['lvt_first_stage']['metrics']
    if (manifest['identity']['case']!='schematic_receiver_tt_25' or not report['diagnostic_complete'] or
        not metrics['passed'] or len(metrics['points'])!=12 or not all(p['passed'] for p in metrics['points'])):
        raise ValueError('LVT static source screen did not pass every original sample')
    expected=source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    if closure_hash((screen/'source.spice').read_text(),'openlvds_receiver_core')!=closure_hash(expected,'openlvds_receiver_core'):
        raise ValueError('LVT static screen characterizes another receiver source')
    files=[screen/n for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn']]
    return {str(p.relative_to(ROOT)):digest(p) for p in files}


def source_gate(screen,static_screen):
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
    return {**{str(p.relative_to(ROOT)):digest(p) for p in files},**static_gate(static_screen)}


def place_monitor(devices):
    moved=[d for d in devices if '__XTRACK__' in d['name']]
    rest=[d for d in devices if d not in moved]
    first=next((i for i,d in enumerate(rest) if '__XIB0__' in d['name']),None)
    if len(moved)!=6 or first is None:raise ValueError('Unexpected unloaded monitor or restoration topology')
    return rest[:first]+moved+rest[first:]


def build(screen,static_screen):
    proofs=source_gate(screen,static_screen)
    source=source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    # Move only the six unloaded monitor devices. Existing device banks keep
    # their relative order, matching the preceding physical placement policy.
    original=physical.draw_macro
    def draw(out,top,ports,devices,library):
        return original(out,top,ports,place_monitor(devices),library)
    try:
        physical.draw_macro=draw
        out,summary=physical.build(source,dict(input_tail_scale=2,decision_scale=1,decision_clamped=False,clamp_variant='unclamped_lvt_restore',clamp_reference=None,replica_monitor_unloaded=True,reference_widths_um=[32,16],parallel_clamp_units=0,
            first_restoration_nfet_model='sky130_fd_pr__nfet_01v8_lvt',restoration_widths_um=[[8,4],[16,8],[16,8]],restoration='Three inverters: P/N widths 8/4, 16/8, 16/8; unchanged final drive and overall polarity',
            placement='Only six unloaded monitor devices moved before first restoration inverter',
            source_screen=str(screen.relative_to(ROOT)),static_screen=str(static_screen.relative_to(ROOT)),source_screen_proofs=proofs),
            [Path(__file__).name,'receiver_lvt_static.py','receiver_lvt_restore_experiment.py','receiver_unclamped_restore_experiment.py','receiver_fast_restore_experiment.py','receiver_vref_clamp_experiment.py','receiver_light_clamp_experiment.py','receiver_light_decision_experiment.py','receiver_strong_clamp_experiment.py','receiver_clamp_experiment.py','layout_receiver_gain_candidate.py','layout_receiver_tail_candidate.py']+
            list(json.loads((static_screen/'manifest.json').read_text())['identity']['code']))
    finally:
        physical.draw_macro=original
    print(json.dumps(dict(output=str(out),passed=summary['passed'])),flush=True)
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('screen',type=Path)
    p.add_argument('--static-screen',type=Path,required=True);a=p.parse_args()
    raise SystemExit(build(a.screen.resolve(),a.static_screen.resolve()))
