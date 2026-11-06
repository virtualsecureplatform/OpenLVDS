#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolated explicit-thread experiment using the pinned native binary translator."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import sys
import time
import run_native_binary_v2 as original

ROOT = original.ROOT


def command(loader, runtime, binary, deck, raw, log, threads):
    if type(threads) is not int or threads not in (1, 2):
        raise ValueError('Thread experiment permits exactly one or two threads')
    return [str(loader), '--library-path', str(runtime), str(binary),
            '-D', 'num_threads=' + str(threads), '-n', '-b', '-r', str(raw),
            '-o', str(log), str(deck)]


def observe(process, raw):
    """Drain output while sampling only this child; observation never stops it."""
    samples = {}
    active = {}
    while True:
        try:
            count = len(list((Path('/proc') / str(process.pid) / 'task').iterdir()))
            if count:
                samples[count] = samples.get(count, 0) + 1
                if raw.exists() and raw.stat().st_size > 65536:
                    active[count] = active.get(count, 0) + 1
        except OSError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=.25)
            return stdout, stderr, samples, active
        except subprocess.TimeoutExpired:
            continue


def run(deck, log, threads):
    deck = deck.resolve()
    log = log.resolve()
    translated, names = original.translate(deck.read_text())
    path = deck.with_suffix('.ngspice.cir')
    raw = deck.with_suffix('.raw')
    receipt = deck.parent / 'runtime.json'
    runtime = ROOT / 'build/tools/ngspice-runtime'
    binary = ROOT / 'build/tools/ngspice-root/usr/bin/ngspice'
    loader = runtime / 'ld-linux-x86-64.so.2'
    argv = command(loader, runtime, binary, path, raw, log, threads)
    if any(p.exists() for p in (path, raw, log, receipt)):
        raise ValueError('Retain prior or partial explicit-thread native evidence')
    manifest = json.loads((ROOT / 'build/tools/ngspice.json').read_text())
    for name, digest in manifest['files'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Changed pinned simulator runtime: ' + name)
    path.write_text(translated)
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    process = subprocess.Popen(argv, cwd=deck.parent, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    stdout, stderr, samples, active = observe(process, raw)
    elapsed = time.monotonic() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    report = dict(configured_threads=threads, observed_thread_count_samples=samples,
        observed_active_thread_count_samples=active,
        active_thread_configuration_observed=bool(active and max(active) == threads),
        wall_seconds=elapsed, child_user_seconds=after.ru_utime-before.ru_utime,
        child_system_seconds=after.ru_stime-before.ru_stime, returncode=process.returncode,
        argv=argv, pinned_runtime_verified=True,
        translator_sha256=hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest(),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        native_transient_validated=False, original_deck_translation_retained=True,
        models_or_tolerances_changed=False,
        electrical_qualification_passed=False, qualified_phy=False,
        scope='Explicit thread-count and contended child runtime observation only; no backend or PHY admission')
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    receipt.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    if process.returncode:
        return process.returncode
    from reduce_rc import number
    stops = re.findall(r'(?im)^\.tran\s+\S+\s+(\S+)', deck.read_text())
    if len(stops) != 1:
        raise ValueError('Require one unchanged complete native transient')
    original.validate(raw, names, number(stops[0]))
    report['native_transient_validated'] = True
    receipt.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--threads', type=int, choices=(1, 2), required=True)
    parser.add_argument('-l', type=Path, required=True)
    parser.add_argument('deck', type=Path)
    args = parser.parse_args()
    sys.exit(run(args.deck, args.l, args.threads))
