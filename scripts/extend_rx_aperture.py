#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend the unchanged native capture aperture to 250 ps on both inputs.

Reuse requires the independently verified original 480-condition table.
Only the 600 new conditions are simulated. No old producer is modified.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
from threading import Event

import numpy as np
import rx_candidate_aperture as original
import rx_aperture_evidence as evidence
from continue_rx_aperture_fair import point_with_lease
from run_ngspice import read_raw
from receiver_static_diagnosis import capture_manifest
from spice_engine import engine, provenance

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'native-rx-aperture-250ps-v1'
NAMESPACE = 'rx_aperture_extended'
SLEWS = (20, 200, 250)
capture = original.capture
sha = evidence.sha
EXTRA = ('extend_rx_aperture.py', 'continue_rx_aperture_fair.py', 'spice_dispatch.py')


def conditions(requirements):
    return [dict(process=p, temperature=t, edge=e, polarity=d, clock_slew_ps=cs,
                 data_slew_ps=ds, kind=k) for p, t, e, d, cs, ds, k in itertools.product(
        requirements['process_corners'], requirements['temperatures_c'], ['rising', 'falling'],
        ['rise', 'fall'], SLEWS, SLEWS, ['setup', 'hold'])]


def fresh_conditions(requirements):
    return [s for s in conditions(requirements) if 250 in (s['clock_slew_ps'], s['data_slew_ps'])]


def prepare(parent):
    if engine() != 'ngspice':
        raise ValueError('Use the pinned ngspice environment')
    if not parent.is_relative_to(ROOT / 'build/characterization/rx_aperture'):
        raise ValueError('Require the original candidate aperture context')
    pm = json.loads((parent / 'manifest.json').read_text()); original.validate(parent, pm)
    # Parent results can still be running. Only immutable context is captured
    # here; no original boundary is reused or admitted until table assembly.
    code = {**pm['identity']['code'], **pm['identity']['candidate_code']}
    code.update({n: sha(ROOT / 'scripts' / n) for n in EXTRA})
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), parent_manifest_sha256=sha(parent / 'manifest.json'),
        code=code, simulator_provenance=provenance(), model=pm['identity']['model'],
        library_sha256=sha(parent / 'library.spice'), requirements_sha256=sha(ROOT / 'requirements.json'),
        slews_ps=list(SLEWS), period_ns=capture.PERIOD_NS, bracket_ps=list(capture.BRACKET_PS),
        resolution_ps=capture.RESOLUTION_PS, guard_ps=capture.GUARD_PS)
    out = ROOT / 'build/characterization' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    from expand_dll_slew_frontends import write_once
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ('library.spice', 'requirements.json'):
            write_once(out / name, (parent / name).read_text())
        (out / 'producers').mkdir(exist_ok=True)
        for name in code:
            write_once(out / 'producers' / name, (ROOT / 'scripts' / name).read_text())
        req = json.loads((out / 'requirements.json').read_text())
        capture_manifest(out / 'manifest.json', dict(identity=identity, conditions=conditions(req),
            fresh_conditions=fresh_conditions(req), clock_mhz=410, supply_v=1.8, load_ff=20, qualified_phy=False))
    return out


def validate(out):
    if not out.is_relative_to(ROOT / 'build/characterization' / NAMESPACE):
        raise ValueError('Require an isolated extended-aperture context')
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; parent = ROOT / i['parent']
    if (out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['version'] != VERSION or i['slews_ps'] != list(SLEWS) or i['simulator_provenance'] != provenance()
            or i['period_ns'] != capture.PERIOD_NS or i['bracket_ps'] != list(capture.BRACKET_PS)
            or i['resolution_ps'] != 5 or i['guard_ps'] != 20
            or m['clock_mhz'] != 410 or m['supply_v'] != 1.8 or m['load_ff'] != 20 or m['qualified_phy'] is not False
            or sha(parent / 'manifest.json') != i['parent_manifest_sha256']
            or sha(out / 'requirements.json') != i['requirements_sha256']
            or sha(out / 'requirements.json') != sha(ROOT / 'requirements.json')
            or sha(out / 'library.spice') != i['library_sha256']
            or (out / 'library.spice').read_bytes() != (parent / 'library.spice').read_bytes()
            or any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items())):
        raise ValueError('Extended aperture context changed')
    pm = json.loads((parent / 'manifest.json').read_text()); original.validate(parent, pm)
    req = json.loads((out / 'requirements.json').read_text())
    expected_code = {**pm['identity']['code'], **pm['identity']['candidate_code'],
                     **{n: sha(ROOT / 'scripts' / n) for n in EXTRA}}
    if (i['model'] != pm['identity']['model'] or i['code'] != expected_code
            or m['conditions'] != conditions(req) or m['fresh_conditions'] != fresh_conditions(req)):
        raise ValueError('Extended aperture model or coverage changed')
    return m


def expected_deck(root, manifest, spec, distance):
    body, timing = capture.fixture(spec, distance, manifest['identity']['model']['ports'])
    pdk = Path(os.environ['PDK_ROOT']) / 'sky130A/libs.tech/ngspice/sky130.lib.spice'
    return (f'OpenLVDS full-RC DDR aperture {capture.condition_id(spec)} {distance:g}ps\n'
        f'.lib "{pdk}" {spec["process"]}\n.include "{root}/library.spice"\n'
        f'.options device temp={spec["temperature"]}\n'
        '.options timeint method=gear reltol=1e-4 abstol=1e-12\n' + body +
        f'.tran 5p {timing["stop_ns"]:.12g}n 0 5p\n'
        '.print tran V(CLK) V(D) V(Q0) V(Q1) V(VALID)\n.end\n')


def witness(root, manifest, spec, distance, passed):
    evidence.verify_witness(root, manifest, spec, distance, passed)
    point = root / capture.condition_id(spec) / ('point_' + f'{distance:.6f}'.replace('-', 'm').replace('.', 'p'))
    if (point / 'bench.cir').read_text() != expected_deck(root, manifest, spec, distance):
        raise ValueError('Aperture witness circuit, load, stimulus or integration step changed')
    names, raw = read_raw(point / 'bench.raw')
    wave, header = capture.read_wave(point / 'bench.cir.prn')
    _, timing = capture.fixture(spec, distance, manifest['identity']['model']['ports'])
    if (not np.isfinite(raw).all() or not capture.complete(wave, timing['stop_ns'])
            or len(raw) != len(wave) or not np.array_equal(wave[:, 0], np.arange(len(raw)))
            or not np.array_equal(wave[:, 1], raw[:, names.index('time')])):
        raise ValueError('Incomplete or inconsistent aperture raw/export trace')
    for label, column in header.items():
        if label.startswith('V(') and not np.array_equal(wave[:, column], raw[:, names.index(label.lower())]):
            raise ValueError('Aperture export differs from the binary waveform')
    return {str((point / n).relative_to(ROOT)): sha(point / n)
            for n in ('summary.json', 'bench.cir', 'bench.raw', 'bench.cir.prn')}


def boundary(root, manifest, spec):
    path = root / capture.condition_id(spec) / 'summary.json'
    result = json.loads(path.read_text())
    if (result.get('passed') is not True or result['spec'] != spec or result['guard_ps'] != 20
            or not 0 < result['passed_ps'] - result['failed_ps'] <= 5
            or result['resolution_ps'] != result['passed_ps'] - result['failed_ps']
            or result['bound_ps'] != capture.guarded_bound(result['passed_ps'])):
        raise ValueError('Invalid extended aperture boundary')
    files = {str(path.relative_to(ROOT)): sha(path)}
    for distance, passed in ((result['failed_ps'], False), (result['passed_ps'], True), (result['bound_ps'], True)):
        files.update(witness(root, manifest, spec, distance, passed))
    return result, files


def assemble(out, write=True):
    m = validate(out); parent = ROOT / m['identity']['parent']
    pm = json.loads((parent / 'manifest.json').read_text())
    # This gate remeasures the complete original matrix; an incomplete parent
    # cannot be replaced by a collection of individually passing prefixes.
    evidence.read_table(parent / 'table.json', m['identity']['model']['netlist_sha256'], 'ss', 40)
    original.check_seeds(parent, pm)
    results = []; files = {str((parent / 'table.json').relative_to(ROOT)): sha(parent / 'table.json')}
    for spec in m['conditions']:
        source = out if 250 in (spec['clock_slew_ps'], spec['data_slew_ps']) else parent
        result, proof = boundary(source, m if source == out else pm, spec)
        results.append(dict(result, witness_root=str(source.relative_to(ROOT))))
        files.update(proof)
    req = json.loads((out / 'requirements.json').read_text()); bounds = {}
    for p, t in itertools.product(req['process_corners'], req['temperatures_c']):
        subset = [r for r in results if r['spec']['process'] == p and r['spec']['temperature'] == t]
        if len(subset) != 72:
            raise ValueError('Extended aperture PVT coverage incomplete')
        bounds[f'{p}_{t}'] = {k + '_ps': max(r['bound_ps'] for r in subset if r['spec']['kind'] == k) for k in ('setup', 'hold')}
    validate(out)
    table = dict(version=VERSION, passed=True, conditions=len(results), reused_conditions=480, new_conditions=600,
        model_sha256=m['identity']['model']['netlist_sha256'], manifest_sha256=sha(out / 'manifest.json'),
        simulator_provenance=provenance(), input_slew_ps=[20, 250], characterized_slews_ps=list(SLEWS),
        clock_mhz=410, load_ff=20, guard_ps=20, resolution_ps=5,
        additional_link_margin_ps=req['minimum_sampling_margin_ps'], bounds=bounds, results=results,
        witness_files=files, qualified_phy=False)
    if write:
        capture_manifest(out / 'table.json', table)
        capture.atomic(out / 'state.json', dict(status='complete', aperture_passed=True, qualified_phy=False))
    return table


def read_table(path, model_sha256, process, temperature):
    path = Path(path).resolve(); out = path.parent
    m = validate(out)
    if m['identity']['model']['netlist_sha256'] != model_sha256:
        raise ValueError('Extended aperture belongs to another capture circuit')
    table = json.loads(path.read_text())
    if table != assemble(out, write=False):
        raise ValueError('Extended aperture table or witnesses changed')
    return dict(qualified=True, table=str(path.relative_to(ROOT)), table_sha256=sha(path),
        model_sha256=model_sha256, **table['bounds'][f'{process}_{temperature}'], guard_ps=20, resolution_ps=5,
        input_slew_ps=[20, 250], consumer_sha256=sha(Path(__file__)), aperture_version=VERSION)


def run(out):
    m = validate(out); stamp = sha(out / 'manifest.json')
    def unchanged():
        if (sha(out / 'manifest.json') != stamp or sha(out / 'library.spice') != m['identity']['library_sha256']
                or any(sha(ROOT / 'scripts' / n) != h for n, h in m['identity']['code'].items())):
            raise ValueError('Extended aperture execution context changed')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / capture.condition_id(s) / 'summary.json').exists() for s in m['fresh_conditions']):
            raise ValueError('Prior extended aperture execution retained; no retry')
        capture.atomic(out / 'state.json', dict(status='running_new_boundaries', new_conditions=600, max_jobs=2, qualified_phy=False))
        old_point = capture.point; failed = Event()
        def point(root, manifest, spec, distance):
            return point_with_lease(root, manifest, spec, distance, old_point, unchanged)
        capture.point = point
        try:
            def worker(spec):
                if failed.is_set():
                    return dict(spec=spec, passed=False, held=True)
                result = capture.search(out, m, spec)
                if not result['passed']:
                    failed.set()
                unchanged()
                return result
            ordered = original.ordered_conditions(m['fresh_conditions'])
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(worker, ordered))
            validate(out)
            if failed.is_set():
                capture_manifest(out / 'incomplete_summary.json', dict(results=results, qualified_phy=False))
                capture.atomic(out / 'state.json', dict(status='held_by_native_failure', qualified_phy=False))
                return 1
        except Exception as error:
            capture.atomic(out / 'state.json', dict(status='held_for_diagnosis', error=str(error), qualified_phy=False))
            raise
        finally:
            capture.point = old_point
        capture.atomic(out / 'state.json', dict(status='new_boundaries_complete', qualified_phy=False))
    if not (ROOT / m['identity']['parent'] / 'table.json').exists():
        return 0  # Assembly remains explicitly gated on the complete parent.
    assemble(out)
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run', 'assemble', 'verify']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); out = a.artifact.resolve()
    if a.action == 'prepare': print(prepare(out), flush=True)
    elif a.action == 'run': raise SystemExit(run(out))
    elif a.action == 'assemble':
        result = assemble(out); print(json.dumps(dict(conditions=result['conditions'], passed=result['passed'], qualified_phy=False)))
    else:
        m = validate(out)
        print(json.dumps(read_table(out / 'table.json', m['identity']['model']['netlist_sha256'], 'ss', 40), indent=2))
