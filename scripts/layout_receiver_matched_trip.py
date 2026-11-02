#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build a source-qualified unit-matched differential-restoration receiver with a local loaded trip reference."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import layout_receiver_variant as physical
import layout_receiver_frontend as reference_layout
import receiver_differential_restore_geometry as geometry
import receiver_matched_trip_clock as clocks
from receiver_layout_reference import cached
from dll_candidate_library import audited

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
TOP = 'openlvds_receiver_core'
sha = clocks.dc.sha


def profile(variant):
    if variant not in clocks.VARIANTS:
        raise ValueError('Select a declared differential-restoration receiver')
    return dict(clamp_variant='matched_trip_restore_'+variant,
        matched_trip_variant=variant, diagnostic_stage='complete_source_DC_and_clock_passed',
        placement=reference_layout.PLACEMENT+'; frontend loads then W8 decision, amplifier, loaded trip reference and restoring chain in stage order; all functional amplifier and trip-reference devices local',
        routing='matched_trip_restore_local_reference_three_decision_buses')


def source_gate(matrix, clock, variant):
    profile(variant)
    proofs = clocks.static_gate(matrix, variant)
    if not clock.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use the selected correction source-clock context')
    m = json.loads((clock/'manifest.json').read_text()); i = m['identity']
    if (i.get('matched_trip_variant') != variant or
            i.get('static_screen') != str(matrix.relative_to(ROOT)) or i.get('static_proofs') != proofs or
            len(m['tasks']) != 3 or {t['id'] for t in m['tasks']} != clocks.clock.CASES or
            not (clock/'summary.json').is_file() or not (clock/'source_clock_admission.json').is_file() or
            any(not (clock/t['id']/'summary.json').is_file() for t in m['tasks'])):
        raise ValueError('Complete all three source-clock controls for this exact correction first')
    with (clock/'.physical_admission.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        clocks.run(clock)  # All controls exist: cached scientific remeasurement only.
    admission = json.loads((clock/'source_clock_admission.json').read_text())
    if (admission.get('source_clock_passed') is not True or
            admission.get('manifest_sha256') != sha(clock/'manifest.json') or
            admission.get('report_sha256') != sha(clock/'summary.json')):
        raise ValueError('Selected correction source-clock admission failed or changed')
    paths = [clock/n for n in ['manifest.json', 'summary.json', 'source_clock_admission.json']]
    for t in m['tasks']:
        paths.extend(clock/t['id']/n for n in list(t['files'])+['summary.json', 'bench.cir.prn'])
    return dict(proofs, **{str(p.relative_to(ROOT)): sha(p) for p in paths})


def build(reference, matrix, clock, variant):
    metadata = profile(variant)
    proofs = source_gate(matrix, clock, variant)
    if not reference.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use the audited original frontend-local LVT geometry')
    report = json.loads((reference/'summary.json').read_text())
    info = json.loads((reference/'extraction.json').read_text())
    if any(report['identity'].get(k) != v for k, v in reference_layout.PROFILE.items()):
        raise ValueError('Expected the original frontend-local reference profile')
    original = clocks.original.source_variant((ROOT/'analog/openlvds.spice').read_text(), True)
    if not report['passed'] or cached(reference, report['identity'], original) != report:
        raise ValueError('Original frontend-local physical evidence changed or failed')
    if (any(sha(ROOT/'scripts'/n) != h for n, h in report['identity']['code'].items()) or
            any(sha(ROOT/n) != h for n, h in report['identity']['source_proofs'].items())):
        raise ValueError('Original frontend-local producer/source evidence changed')
    audited(reference, info); gds = ROOT/report['designs'][TOP]['gds']
    if sha(gds) != info['gds_sha256'] or sha(reference/'candidate.spice') != info['source_sha256']:
        raise ValueError('Original frontend extraction source/GDS binding changed')
    source = clocks.dc.transform(original, variant)
    dc_manifest = json.loads((matrix/'manifest.json').read_text())
    if hashlib.sha256(source.encode()).hexdigest() != dc_manifest['identity']['candidate_sha256'][variant]:
        raise ValueError('Physical source differs from the admitted DC candidate')
    metadata.update(source_proofs=proofs, source_matrix=str(matrix.relative_to(ROOT)),
        source_clock=str(clock.relative_to(ROOT)), reference_layout=str(reference.relative_to(ROOT)),
        reference_summary_sha256=sha(reference/'summary.json'), reference_gds_sha256=sha(gds),
        reference_extraction_sha256=sha(reference/'extraction.json'), reference_audit_sha256=sha(reference/'rc_audit.json'))
    producers = set(report['identity']['code']) | {NAME, 'receiver_matched_trip_clock.py',
        'receiver_restore_threshold_clock.py', 'receiver_restore_threshold.py', 'matrix_receiver_matched_trip.py', 'screen_receiver_matched_trip.py', 'receiver_differential_restore.py', 'receiver_matched_trip_restore.py', 'receiver_gain_balance.py', 'receiver_soft_common_mode.py', 'receiver_lvt_restore_experiment.py', 'dll_candidate_library.py', 'receiver_soft_frontend_geometry.py', 'receiver_differential_restore_geometry.py'}
    names = producers | {'layout_receiver_variant.py', 'layout.py', 'lvs_utils.py', 'spice_library.py'}
    identity = dict(metadata, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)})
    out = ROOT/'build/diagnostics/receiver_layout'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = cached(out, identity, source)
        if result is not None:
            return out, result
        for n in names:
            p = out/'producer_snapshot'/n; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((ROOT/'scripts'/n).read_bytes())
        previous = physical.draw_macro
        try:
            physical.draw_macro = geometry.draw_macro
            actual, result = physical.build(source, metadata, producers)
        finally:
            physical.draw_macro = previous
        if actual != out or result['identity'] != identity:
            raise ValueError('Differential-restoration frontend physical identity changed')
        files = [out/(TOP+s) for s in ['.gds', '.sch.spice', '.lvs.log', '.drc.txt', '.drc_count.txt']]
        files += [out/'candidate.spice', out/'summary.json']
        (out/'physical_cache.json').write_text(json.dumps(dict(files={p.name: sha(p) for p in files}), indent=2)+'\n')
    return out, result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('reference', type=Path)
    p.add_argument('--dc-matrix', type=Path, required=True); p.add_argument('--source-clock', type=Path, required=True)
    p.add_argument('--variant', choices=clocks.VARIANTS, required=True); a = p.parse_args()
    out, result = build(a.reference.resolve(), a.dc_matrix.resolve(), a.source_clock.resolve(), a.variant)
    print(json.dumps(dict(output=str(out), passed=result['passed'], qualified_phy=False)), flush=True)
    raise SystemExit(0 if result['passed'] else 1)
