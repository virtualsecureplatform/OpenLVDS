#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit Xyce runtime and numerical profiles for new 300 MHz campaigns."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path('/opt/xyce/bin/Xyce')
EXPECTED_BINARY = 'a8a679da37cd5da306745acaf1bd178cccc63cd0776d531eb15c5ecdff8e83bf'
PROFILES = {
    'baseline': dict(reltol=1e-4, abstol=1e-9, maxstep_ps=2),
    'refined': dict(reltol=2e-5, abstol=1e-10, maxstep_ps=1),
    'strict': dict(reltol=1e-5, abstol=1e-12, maxstep_ps=.5),
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def runtime():
    if sha(BINARY) != EXPECTED_BINARY:
        raise ValueError('Xyce binary differs from selected stock 7.10 runtime')
    result = subprocess.run(['ldd', str(BINARY)], check=True, capture_output=True, text=True)
    libraries = sorted(set(re.findall(r'(?:=>\s+)?(/[^\s()]+)', result.stdout)))
    if not libraries or 'not found' in result.stdout:
        raise ValueError('Incomplete Xyce shared library closure')
    files = {str(p): sha(p) for p in [BINARY, *map(Path, libraries)]}
    return dict(binary=str(BINARY), solver='KLU', files=files,
                version=subprocess.run([str(BINARY), '-v'], check=True, capture_output=True, text=True).stdout.strip(),
                threads=1)


def command(log, deck):
    return [str(BINARY), '-linsolv', 'KLU', '-l', str(log), str(deck)]


def environment():
    return dict(os.environ, OMP_NUM_THREADS='1', OMP_THREAD_LIMIT='1', OPENBLAS_NUM_THREADS='1')


def options(profile):
    p = PROFILES[profile]
    return ('.options parser model_binning=true\n'
            f'.options nonlin reltol={p["reltol"]:.17g} abstol={p["abstol"]:.17g}\n'
            f'.options timeint method=gear reltol={p["reltol"]:.17g} abstol={p["abstol"]:.17g}\n')


def warnings(text):
    flat = re.sub(r'\s+', ' ', text)
    return dict(version_substitutions=re.findall(
        r'version ([\d.]+) which is older than the oldest version supported in Xyce \(([\d.]+)\)', flat),
        occurrences=len(re.findall('warning', text, re.I)),
        lines=[line for line in text.splitlines() if re.search('warning|ignor|unrecognized|unknown|clamp', line, re.I)],
        complete_logs_required=True)


if __name__ == '__main__':
    print(json.dumps(runtime(), indent=2))
