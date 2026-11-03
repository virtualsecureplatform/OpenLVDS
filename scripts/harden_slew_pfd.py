#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run isolated PFD placement/routing for a verified native frontend winner.

This produces physical diagnostic evidence. Strict extracted LVS, routed-RC
matching and native electrical qualification remain independent gates.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pfd_slew_policy as policy
import slew_pfd_floorplan as floorplan

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'slew_pfd_physical'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
FINAL = ('nl/lvds_pfd.nl.v', 'def/lvds_pfd.def', 'gds/lvds_pfd.gds',
         'spice/lvds_pfd.spice', 'metrics.json')
DRC = ('route__drc_errors', 'magic__drc_error__count', 'klayout__drc_error__count')


def atomic(path, value):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n'); temp.replace(path)


def write_once(path, text):
    if path.exists():
        if path.read_text() != text: raise ValueError('Prepared physical input changed: ' + str(path))
    else: path.write_text(text)


def capture_manifest(path, value):
    if path.exists():
        encode = lambda item: json.dumps(item, sort_keys=True, allow_nan=False)
        if encode(json.loads(path.read_text())) != encode(value): raise ValueError('Physical manifest changed')
    else: atomic(path, value)


def source_gate(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics/slew_pfd_source'):
        raise ValueError('Require the admitted physical-source artifact')
    # The Nix LibreLane interpreter has no NumPy. The existing container system
    # interpreter validates the immutable electrical evidence in its own
    # scientific environment; never put Python 3.13 packages on its 3.12 path.
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    result = subprocess.run(['/usr/bin/python3', str(ROOT / 'scripts/prepare_slew_pfd.py'), 'bound', str(parent)],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode: raise ValueError('Prepared source validation failed: ' + result.stderr[-2000:])
    return json.loads(result.stdout)


def tools():
    spec = importlib.util.find_spec('librelane')
    if spec is None or not spec.origin or not os.environ.get('PDK_ROOT'):
        raise ValueError('Use scripts/env.sh --tools --ngspice python3')
    package = Path(spec.origin).parent
    paths = [package / n for n in ('__init__.py', 'flows/classic.py', 'steps/common_variables.py',
                                   'steps/odb.py', 'scripts/odbpy/placers.py', 'scripts/odbpy/apply_def_template.py')]
    return dict(python=sys.executable, source_validator_python_sha256=sha(Path('/usr/bin/python3')),
                pdk_root=os.environ['PDK_ROOT'],
                package_files={str(p): sha(p) for p in paths})


def generated(out, parent, baseline, base, variant):
    target = floorplan.plan(baseline, variant); archive = out / 'inputs'
    shared = ROOT / 'thirdparties/OpenPLL/sky130/sky130_fd_sc_hd_pll_blackbox.v'
    cfg = floorplan.configuration(base, target, source=archive / 'lvds_pfd.v',
                                 blackboxes=archive / 'pfd_blackboxes.v', shared_models=archive / 'pll_blackbox.v',
                                 sdc=archive / 'pfd.sdc', template=archive / 'pins.def')
    encode = lambda item: json.dumps(item, indent=2, allow_nan=False) + '\n'
    return {
        'inputs/lvds_pfd.v': (parent / 'lvds_pfd.v').read_text(),
        'inputs/pfd_blackboxes.v': (parent / 'pfd_blackboxes.v').read_text() + (parent / 'slew_blackboxes.v').read_text(),
        'inputs/pll_blackbox.v': shared.read_text(), 'inputs/pfd.sdc': (parent / 'pfd.sdc').read_text(),
        'inputs/pins.def': target['pin_template'], 'target.json': encode(target),
        'config.json': encode(cfg), 'inputs/config.json': encode(cfg)}


def prepare(parent, baseline):
    sm = source_gate(parent); base_summary = json.loads((baseline / 'summary.json').read_text())
    if not base_summary.get('passed'): raise ValueError('Require the retained physical baseline for its row grid')
    definition = ROOT / base_summary['run'] / 'final/def/lvds_pfd.def'
    base = json.loads((baseline / 'config.json').read_text())
    inputs = dict(sm['identity']['inputs'])
    paths = [parent / 'manifest.json'] + [parent / n for n in sm['files']]
    paths += [baseline / 'summary.json', baseline / 'config.json', definition,
              ROOT / 'thirdparties/OpenPLL/sky130/sky130_fd_sc_hd_pll_blackbox.v']
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    collateral = {str(Path(p)): sha(Path(p)) for paths in base['LIB'].values() for p in paths}
    code = dict(sm['identity']['code'])
    for n in (Path(__file__).name, 'slew_pfd_floorplan.py', 'receiver_static_diagnosis.py', 'dll_campaign.py'):
        code[n] = sha(ROOT / 'scripts' / n)
    identity = dict(parent=str(parent.relative_to(ROOT)), baseline=str(baseline.relative_to(ROOT)),
                    baseline_def=str(definition.relative_to(ROOT)), variant=sm['identity']['variant'],
                    policy=sm['identity']['policy'], coverage_recipe=sm['identity']['coverage_recipe'],
                    inputs=inputs, code=code, tools=tools(), collateral=collateral,
                    scope='Verified source winner, preserved named cells, translated placement and input pin template. Placement/routing diagnostic only; strict extracted LVS, routed matching, expanded native/loop/stability and PHY gates remain required.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (out / 'inputs').mkdir(exist_ok=True); (out / 'producers').mkdir(exist_ok=True)
        files = generated(out, parent, definition.read_text(), base, identity['variant'])
        for n, text in files.items(): write_once(out / n, text)
        for n in code: write_once(out / 'producers' / n, (ROOT / 'scripts' / n).read_text())
        capture_manifest(out / 'manifest.json', dict(identity=identity, files={n: sha(out / n) for n in files},
                                                    qualified_phy=False, physical_admission=False))
    return out


def bound(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE) or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
            m['qualified_phy'] is not False or m['physical_admission'] is not False or tools() != i['tools'] or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items()) or
            any(sha(Path(n)) != h for n, h in i['collateral'].items()) or
            any(sha(out / n) != h for n, h in m['files'].items())):
        raise ValueError('Physical PFD context changed')
    expected = generated(out, ROOT / i['parent'], (ROOT / i['baseline_def']).read_text(),
                         json.loads((ROOT / i['baseline'] / 'config.json').read_text()), i['variant'])
    if set(m['files']) != set(expected) or any((out / n).read_text() != text for n, text in expected.items()):
        raise ValueError('Physical PFD configuration or archived source changed')
    return m


def source_stamp(out):
    # Preserve the established captured_inputs() archive contract. The extra
    # frontend blackboxes are inside the archived pfd_blackboxes.v; the full
    # manifest additionally binds the shared models and DEF template.
    return hashlib.sha256(b''.join((out / 'inputs' / n).read_bytes() for n in
                                  ('lvds_pfd.v', 'pfd_blackboxes.v', 'pfd.sdc', 'config.json'))).hexdigest()


def run_directory(out): return out / 'runs' / ('slew-' + source_stamp(out)[:12])


def assess(out, m, returncode):
    final = run_directory(out) / 'final'
    missing = [n for n in FINAL if not (final / n).is_file() or (final / n).stat().st_size == 0]
    if not (out / 'flow.log').is_file() or (out / 'flow.log').stat().st_size == 0: missing.append('flow.log')
    metrics = json.loads((final / 'metrics.json').read_text()) if 'metrics.json' not in missing else {}
    topology = 'nl/lvds_pfd.nl.v' not in missing and policy.retained((final / 'nl/lvds_pfd.nl.v').read_text(), m['identity']['variant'])
    geometry = floorplan.check((final / 'def/lvds_pfd.def').read_text(), json.loads((out / 'target.json').read_text())) if 'def/lvds_pfd.def' not in missing else dict(placement_matched=False, errors=['Missing final DEF'], route_matching_verified=False, physical_admission=False, qualified_phy=False)
    drc = all(type(metrics.get(n)) in (int, float) and metrics[n] == 0 for n in DRC)
    passed = bool(returncode == 0 and not missing and topology and geometry['placement_matched'] and drc)
    return dict(passed=passed, returncode=returncode, source_sha256=source_stamp(out),
                run=str(run_directory(out).relative_to(ROOT)), input_archive=str((out / 'inputs').relative_to(ROOT)),
                inputs_unchanged=True, interface_verified=bool(topology), delay_cells_absent=bool(topology),
                pfd_policy=m['identity']['policy'], variant=m['identity']['variant'],
                metrics=metrics, geometry=geometry, zero_drc_passed=drc, missing_outputs=missing,
                strict_extracted_lvs_verified=False, route_matching_verified=False,
                physical_admission=False, qualified_phy=False, scope=m['identity']['scope'])


def output_files(out):
    return [p for p in [out / 'flow.log', *(run_directory(out) / 'final' / n for n in FINAL)] if p.is_file()]


def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if any((out / n).exists() for n in ('state.json', 'flow.log', 'runs', 'summary.json')):
            raise ValueError('Partial physical output retained; no retry')
        try:
            atomic(out / 'state.json', dict(status='running_placement_route', qualified_phy=False))
            command = [sys.executable, '-m', 'librelane', '--manual-pdk', '--pdk-root', os.environ['PDK_ROOT'],
                       '-p', 'sky130A', '-s', 'sky130_fd_sc_hd', '--condensed', '--hide-progress-bar',
                       '--run-tag', run_directory(out).name, str(out / 'config.json')]
            with (out / 'flow.log').open('w') as log:
                process = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT)
            bound(out)
            if sha(out / 'manifest.json') != stamp: raise ValueError('Physical manifest changed during execution')
            r = dict(assess(out, m, process.returncode), manifest_sha256=stamp,
                     files={str(p.relative_to(out)): sha(p) for p in output_files(out)})
            capture_manifest(out / 'summary.json', r)
            atomic(out / 'state.json', dict(status='physical_diagnostic_passed' if r['passed'] else 'held_physical_diagnostic_failed', qualified_phy=False))
            return r
        except Exception as e:
            atomic(out / 'state.json', dict(status='held_for_diagnosis', error=str(e), qualified_phy=False))
            raise


def verify(out):
    m = bound(out); r = json.loads((out / 'summary.json').read_text()); stamp = sha(out / 'manifest.json')
    files = {str(p.relative_to(out)): sha(p) for p in output_files(out)}
    expected = dict(assess(out, m, r['returncode']), manifest_sha256=stamp, files=files)
    if expected != r: raise ValueError('Physical PFD result changed')
    bound(out); return r


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run', 'verify'])
    p.add_argument('artifact', type=Path); p.add_argument('--baseline', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        if not a.baseline: p.error('--baseline required')
        result = prepare(a.artifact.resolve(), a.baseline.resolve())
    else: result = globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
