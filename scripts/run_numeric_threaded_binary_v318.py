#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Set ngspice's numeric OpenMP variable through an isolated startup file."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import struct
import subprocess
import sys
import time
import run_native_binary_v2 as original

ROOT = original.ROOT
INIT_DIRECTORY = 'thread-init-v318'


def startup_text(threads):
    if type(threads) is not int or threads not in (1, 2):
        raise ValueError('Numeric thread experiment permits exactly one or two threads')
    return 'set num_threads=' + str(threads) + '\necho OPENLVDS_NUMERIC_INIT_V318_' + str(threads) + '\n'


def runtime():
    manifest = json.loads((ROOT / 'build/tools/ngspice.json').read_text())
    for name, expected in manifest['files'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Changed pinned simulator runtime: ' + name)
    library = ROOT / 'build/tools/ngspice-runtime'
    return library / 'ld-linux-x86-64.so.2', library, ROOT / 'build/tools/ngspice-root/usr/bin/ngspice'


def command(loader, library, binary, deck, raw, log):
    # -D makes CP_STRING, while CKTsetup reads CP_NUM. No -n: only the
    # private SPICE_USERINIT_DIR below is read before circuit setup.
    return [str(loader), '--library-path', str(library), str(binary),
            '-b', '-r', str(raw), '-o', str(log), str(deck)]


def initialization(folder, threads):
    text = startup_text(threads)
    directory = folder / INIT_DIRECTORY
    directory.mkdir(exist_ok=False)
    path = directory / '.spiceinit'
    path.write_text(text)
    env = dict(os.environ, SPICE_USERINIT_DIR=str(directory))
    return path, hashlib.sha256(text.encode()).hexdigest(), env


def active_progress(raw):
    """Require actual positive transient time, not just a large raw header."""
    with raw.open('rb') as stream:
        header = b''
        while b'Binary:\n' not in header:
            block = stream.read(65536)
            if not block or len(header) > 64 * 1024 * 1024:
                return False
            header += block
        offset = header.index(b'Binary:\n') + 8
        text = header[:offset].decode()
        count = int(re.search(r'No\. Variables:\s*(\d+)', text)[1])
        names = [m[1].lower() for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$', text, re.M)]
        if len(names) != count or 'time' not in names or 'complex' in text.lower():
            return False
        rows = (raw.stat().st_size - offset) // (8 * count)
        if rows < 2:
            return False
        stream.seek(offset + ((rows - 1) * count + names.index('time')) * 8)
        value = stream.read(8)
        return bool(len(value) == 8 and 0 < struct.unpack('<d', value)[0] < float('inf'))


def observe(process, raw):
    samples, active = {}, {}
    while True:
        try:
            count = len(list((Path('/proc') / str(process.pid) / 'task').iterdir()))
            if count:
                samples[count] = samples.get(count, 0) + 1
                if raw.exists() and active_progress(raw):
                    active[count] = active.get(count, 0) + 1
        except (OSError, ValueError, IndexError, UnicodeDecodeError, struct.error, TypeError):
            pass
        try:
            stdout, stderr = process.communicate(timeout=.25)
            return stdout, stderr, samples, active
        except subprocess.TimeoutExpired:
            continue


def startup_check(folder, threads):
    """Frontend-only check: no model, operating point, transient or raw file."""
    folder = folder.resolve()
    folder.mkdir(exist_ok=False)
    path, digest, env = initialization(folder, threads)
    loader, library, binary = runtime()
    deck = folder / 'frontend.cir'
    deck.write_text('OpenLVDS numeric startup frontend check\n.control\n'
        'echo OPENLVDS_NUMERIC_THREAD_VALUE=$num_threads\nquit\n.endc\n.end\n')
    process = subprocess.run([str(loader), '--library-path', str(library), str(binary), '-b', str(deck)],
                             cwd=folder, env=env, capture_output=True, text=True)
    output = process.stdout + process.stderr
    passed = bool(process.returncode == 0 and 'OPENLVDS_NUMERIC_INIT_V318_' + str(threads) in output
                  and 'OPENLVDS_NUMERIC_THREAD_VALUE=' + str(threads) in output
                  and hashlib.sha256(path.read_bytes()).hexdigest() == digest and 'Error:' not in output)
    (folder / 'console.log').write_text(output)
    report = dict(frontend_only=True, no_native_analysis_performed=True, configured_threads=threads,
        private_startup_loaded=passed, startup_sha256=digest, returncode=process.returncode,
        pinned_runtime_verified=True, active_thread_configuration_observed=False,
        native_transient_validated=False, backend_admitted=False, qualified_phy=False)
    (folder / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    if not passed:
        raise ValueError('Private numeric startup frontend check failed')
    return report


def run(deck, log, threads):
    startup_text(threads)
    deck, log = deck.resolve(), log.resolve()
    path, raw, receipt = deck.with_suffix('.ngspice.cir'), deck.with_suffix('.raw'), deck.parent / 'runtime.json'
    if any(p.exists() for p in (path, raw, log, receipt, deck.parent / INIT_DIRECTORY)):
        raise ValueError('Retain prior or partial numeric-thread native evidence')
    translated, names = original.translate(deck.read_text())
    loader, library, binary = runtime()
    startup, startup_hash, env = initialization(deck.parent, threads)
    path.write_text(translated)
    argv = command(loader, library, binary, path, raw, log)
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    process = subprocess.Popen(argv, cwd=deck.parent, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr, samples, active = observe(process, raw)
    elapsed = time.monotonic() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    output = stdout + stderr + (log.read_text() if log.exists() else '')
    loaded = 'OPENLVDS_NUMERIC_INIT_V318_' + str(threads) in output
    try:
        unchanged = hashlib.sha256(startup.read_bytes()).hexdigest() == startup_hash
    except OSError:
        unchanged = False
    report = dict(configured_threads=threads, observed_thread_count_samples=samples,
        observed_active_thread_count_samples=active,
        active_thread_configuration_observed=bool(active and max(active) == threads),
        private_numeric_thread_init_loaded=loaded, private_numeric_thread_init_unchanged=unchanged,
        startup_path=str(startup), startup_sha256=startup_hash,
        wall_seconds=elapsed, child_user_seconds=after.ru_utime - before.ru_utime,
        child_system_seconds=after.ru_stime - before.ru_stime, returncode=process.returncode,
        argv=argv, pinned_runtime_verified=True,
        translator_sha256=hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest(),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        translated_deck_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        native_transient_validated=False, original_deck_translation_retained=path.read_text() == translated,
        models_or_tolerances_changed=False, backend_admitted=False,
        electrical_qualification_passed=False, qualified_phy=False,
        scope='Private numeric OpenMP setting and contended runtime observation only; no backend or PHY admission')
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    receipt.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    if process.returncode:
        return process.returncode
    from reduce_rc import number
    stops = re.findall(r'(?im)^\.tran\s+\S+\s+(\S+)', deck.read_text())
    if len(stops) != 1:
        raise ValueError('Require one unchanged complete native transient')
    original.validate(raw, names, number(stops[0]))
    report['native_transient_validated'] = True
    receipt.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    if not loaded or not unchanged or not report['original_deck_translation_retained']:
        raise ValueError('Private numeric thread startup did not remain verified')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--threads', type=int, choices=(1, 2), required=True)
    parser.add_argument('-l', type=Path, required=True)
    parser.add_argument('deck', type=Path)
    args = parser.parse_args()
    sys.exit(run(args.deck, args.l, args.threads))
