#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native thread parity using verified numeric startup, never backend adoption."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_native_thread_count_v314 as base
import run_numeric_threaded_binary_v318 as runner
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT = base.ROOT
sha = base.sha
source = base.source
VERSION = 'full-native-numeric-private-init-thread-parity-and-runtime-v319.1'
CONTEXT = 'numeric_native_threads_v319'
SCOPE = ('Private numeric OpenMP variable, exact original native SS40/410MHz fine31 '
         'endpoints and paired 40% control; unchanged binary/translation/PDK/KLU/tolerances, '
         'no live backend change, routed-bank/PVT/DLL/PHY admission')
plan = base.plan
parity = base.parity


def require_audit(folder):
    report = json.loads((folder / 'summary.json').read_text())
    if (folder.parent != ROOT / 'build/reports/numeric_thread_startup_v318'
            or report['version'] != 'ngspice42-cli-string-versus-private-numeric-startup-audit-v318.1'
            or report['source_package_version'] != '42+ds-3build1'
            or report.get('frontend_initialization_verified') is not True
            or report.get('full_native_numeric_thread_configuration_verified') is not False
            or report.get('backend_admitted') is not False or report.get('qualified_phy') is not False
            or any(sha(ROOT / n) != h for n, h in report['inputs'].items())):
        raise ValueError('Require unchanged source/host-observation/private-startup audit')
    legacy = report['legacy_process']
    argv = legacy['argv']
    before = {r['tid']: r for r in legacy['first_snapshot']}
    after = legacy['second_snapshot']
    if (legacy['actual_threads'] != 2 or legacy['positive_native_progress_observed'] is not True
            or legacy['healthy_process_unchanged'] is not True
            or legacy['observation_namespace'] != 'host/proc'
            or '-D' not in argv or argv[argv.index('-D') + 1] != 'num_threads=1'
            or len(after) != 2 or any(r['tid'] not in before or r['cpu_ticks'] <= before[r['tid']]['cpu_ticks'] for r in after)):
        raise ValueError('Require actual old string-option mismatch with two advancing workers')
    source_manifest = json.loads((ROOT / report['source_manifest']).read_text())
    archives = {r['name']: r['sha256'] for r in source_manifest['downloads']}
    if archives != {
        'ngspice_42+ds.orig.tar.gz': 'cae144ba1d28a56a867e09b9d7665fdf71182e568300e379803786fb0c3165b7',
        'ngspice_42+ds-3build1.debian.tar.xz': 'dce5ec571f69f80bea74804eb4ad98e314e54c25a3cb86d121a8f1904a3be5c5'}:
        raise ValueError('Official matching package source archive hashes changed')
    for threads in (1, 2):
        result = report['frontend_checks'][str(threads)]
        if (result['configured_threads'] != threads or result['private_startup_loaded'] is not True
                or result['frontend_only'] is not True or result['no_native_analysis_performed'] is not True
                or result['native_transient_validated'] is not False
                or (folder / str(threads) / runner.INIT_DIRECTORY / '.spiceinit').read_text() != runner.startup_text(threads)
                or json.loads((folder / str(threads) / 'summary.json').read_text()) != result):
            raise ValueError('Require both isolated numeric startup frontend checks')
    return [folder / 'summary.json', *[ROOT / n for n in report['inputs']]]


def guarded_inputs(inputs):
    return {n: h for n, h in inputs.items()
            if not (Path(n).suffix == '.raw' and Path(n).parts[:2] == ('build', 'diagnostics'))}


def prepare(parent, audit):
    paths = require_audit(audit)
    manifest = source.bound(parent)
    previous = manifest['identity']
    references, native_paths = base.references(parent, manifest)
    if engine() != 'ngspice' or provenance() != previous['simulator']:
        raise ValueError('Require the exact original pinned native runtime')
    translations = {}
    for case_id in ('1', '2'):
        translated, _ = runner.original.translate((parent / case_id / 'bench.cir').read_text())
        translations[case_id] = hashlib.sha256(translated.encode()).hexdigest()
        if translations[case_id] != references[case_id]['row']['files']['bench.ngspice.cir']:
            raise ValueError('Original circuit translation changed')
    paths += native_paths + [parent / 'manifest.json', parent / 'bank.spice']
    paths += [ROOT / n for n in previous['inputs']]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT / 'scripts'})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}
    identity = dict(previous, version=VERSION, parent=str(parent.relative_to(ROOT)),
        audit=str(audit.relative_to(ROOT)), references=references, plan=plan(),
        inputs=inputs, guarded_inputs=guarded_inputs(inputs), translations=translations,
        initialization_recipes={str(n): runner.startup_text(n) for n in (1, 2)},
        timing_tolerance_ps=base.TIMING_TOLERANCE_PS, voltage_tolerance_v=base.VOLTAGE_TOLERANCE_V,
        max_workers=1, priority=2, scope=SCOPE)
    out = ROOT / 'build/diagnostics' / CONTEXT / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    tasks = []
    for k, (case_id, threads) in enumerate(plan()):
        folder = out / str(k)
        folder.mkdir()
        (folder / 'bench.cir').write_bytes((parent / case_id / 'bench.cir').read_bytes())
        tasks.append(dict(id=str(k), source_id=case_id, threads=threads,
            spec=references[case_id]['row']['spec'], deck_sha256=sha(folder / 'bench.cir')))
    atomic(out / 'manifest.json', dict(identity=identity, tasks=tasks, backend_admitted=False, qualified_phy=False))
    return out


def bound(out, full=True):
    manifest = json.loads((out / 'manifest.json').read_text())
    i = manifest['identity']
    if (out.parent != ROOT / 'build/diagnostics' / CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['plan'] != [list(p) for p in plan()] or i['max_workers'] != 1 or i['priority'] != 2
            or manifest['backend_admitted'] is not False or manifest['qualified_phy'] is not False
            or i['scope'] != SCOPE or i['guarded_inputs'] != guarded_inputs(i['inputs'])
            or i['initialization_recipes'] != {str(n): runner.startup_text(n) for n in (1, 2)}
            or i['timing_tolerance_ps'] != base.TIMING_TOLERANCE_PS
            or i['voltage_tolerance_v'] != base.VOLTAGE_TOLERANCE_V
            or engine() != 'ngspice' or provenance() != i['simulator']
            or any(sha(ROOT / n) != h for n, h in (i['inputs'] if full else i['guarded_inputs']).items())
            or any(sha(Path(n)) != h for n, h in {**i['pdk_files'], **i['external_files']}.items())
            or len(manifest['tasks']) != 3):
        raise ValueError('Private numeric-thread native experiment changed')
    for k, (case_id, threads) in enumerate(plan()):
        path = out / str(k) / 'bench.cir'
        translated, _ = runner.original.translate(path.read_text())
        if (manifest['tasks'][k] != dict(id=str(k), source_id=case_id, threads=threads,
                spec=i['references'][case_id]['row']['spec'], deck_sha256=sha(path))
                or path.read_bytes() != (ROOT / i['parent'] / case_id / 'bench.cir').read_bytes()
                or hashlib.sha256(translated.encode()).hexdigest() != i['translations'][case_id]):
            raise ValueError('Original native circuit or translation changed')
    return manifest


def compare(rows):
    result = base.compare(rows)
    if result is None:
        return None
    initialization = all(r['runtime']['private_numeric_thread_init_loaded']
        and r['runtime']['private_numeric_thread_init_unchanged']
        and r['runtime']['original_deck_translation_retained']
        and r['runtime']['pinned_runtime_verified']
        and r['runtime']['models_or_tolerances_changed'] is False for r in rows)
    configured = result['configured_thread_counts_observed'] and initialization
    result['private_numeric_initialization_verified'] = initialization
    result['configured_thread_counts_observed'] = configured
    if not configured or not result['full_native_metric_parity_passed']:
        result['paired_40_percent_two_over_one_wall_ratio'] = None
        result['single_thread_faster_on_paired_case'] = False
    return result


def run(out):
    if (out / 'state.json').exists():
        raise ValueError('Retain previous or partial numeric-thread experiment')
    manifest = bound(out)
    i = manifest['identity']
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists():
            raise ValueError('Retain previous or partial numeric-thread experiment')
        atomic(out / 'state.json', dict(status='running', backend_admitted=False, qualified_phy=False))
        rows = []
        try:
            for task in manifest['tasks']:
                folder = out / task['id']
                result = error = runtime = comparison = None
                try:
                    with lease(ROOT, priority=2, label=CONTEXT + '_' + task['id']):
                        bound(out, full=False)
                        process = subprocess.run([sys.executable, str(ROOT / 'scripts/run_numeric_threaded_binary_v318.py'),
                            '--threads', str(task['threads']), '-l', str(folder / 'ngspice.log'), str(folder / 'bench.cir')],
                            capture_output=True, text=True)
                    (folder / 'console.log').write_text(process.stdout + process.stderr)
                    if (folder / 'runtime.json').exists():
                        runtime = json.loads((folder / 'runtime.json').read_text())
                    process.check_returncode()
                    startup = folder / runner.INIT_DIRECTORY / '.spiceinit'
                    if (runtime['startup_path'] != str(startup) or startup.read_text() != runner.startup_text(task['threads'])
                            or runtime['startup_sha256'] != sha(startup)
                            or runtime['translated_deck_sha256'] != i['translations'][task['source_id']]):
                        raise ValueError('Actual numeric initialization or original translation changed')
                    result = source.measure(folder, i, task['spec'])
                    comparison = parity(result, i['references'][task['source_id']]['row']['result'])
                except Exception as exception:
                    error = str(exception)
                row = dict(task=task, result=result, runtime=runtime, parity=comparison, error=error,
                    files={str(p.relative_to(folder)): sha(p) for p in folder.rglob('*') if p.is_file()})
                atomic(folder / 'summary.json', row)
                rows.append(row)
            bound(out)
            atomic(out / 'summary.json', dict(rows=rows, comparison=compare(rows), scope=SCOPE,
                backend_admitted=False, qualified_phy=False))
            atomic(out / 'state.json', dict(status='complete', cases=3,
                errors=sum(r['error'] is not None for r in rows), backend_admitted=False, qualified_phy=False))
        except Exception as exception:
            atomic(out / 'state.json', dict(status='failed', error=str(exception), backend_admitted=False, qualified_phy=False))
            raise
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prepare_parser = sub.add_parser('prepare')
    prepare_parser.add_argument('parent', type=Path)
    prepare_parser.add_argument('audit', type=Path)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.parent.resolve(), args.audit.resolve()), flush=True)
    else:
        print(run(args.artifact.resolve()), flush=True)
