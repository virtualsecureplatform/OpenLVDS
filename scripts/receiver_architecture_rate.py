#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare nominal receiver architectures in the original isolated rate fixture.

This measures the analog receiver into 100 fF without a digital capture core.
It is independent of the selected-pin/native-RX replay calibration and cannot
admit a complete PHY or an extracted receiver.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import receiver_architecture_observations as observed
from dll_campaign import atomic
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_probes import ProbeNetwork
from verify_analog import receiver_rate_metrics
from verify_component_evidence import check_case

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
CODE = {NAME, 'verify_analog.py', 'verify_component_evidence.py', 'evidence_scope.py',
        'spice_dispatch.py', 'spice_probes.py'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(rate, static, old, new):
    """Retain the original rate stimulus, load and probes from static observation."""
    include = f'.include "{old}/source.spice"'
    if rate.count(include) != 1:
        raise ValueError('Ambiguous original rate source')
    deck = rate.replace(include, f'.include "{new}/source.spice"')
    if deck.count('.tran 10p 60n 0 100p') != 1:
        raise ValueError('Unexpected original rate integration policy')
    deck = deck.replace('.tran 10p 60n 0 100p', '.tran 5p 60n 0 1p')
    # The observed static source contains ideal current meters. Reuse its
    # exact probes and unloaded supply-current exports, without changing load.
    prints = re.findall(r'(?im)^\.print tran[^\n]*$', static)
    meters = re.findall(r'(?m)^HOBS_(?:IO|DIG) .*$', static)
    if len(prints) != 1 or len(meters) != 2:
        raise ValueError('Missing nominal current observation probes')
    if not prints[0].startswith('.print tran V(P) V(N) V(Q) '):
        raise ValueError('Unexpected rate observation column order')
    deck, count = re.subn(r'(?im)^\.print tran[^\n]*$', lambda _: prints[0], deck)
    if count != 1:
        raise ValueError('Ambiguous rate probes')
    deck, count = re.subn(r'(?im)^\.end\s*$', '\n'.join(meters)+'\n.end', deck)
    if count != 1:
        raise ValueError('Ambiguous rate fixture end')
    return deck


def prepare(sanity):
    if engine() != 'ngspice' or not sanity.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_static'):
        raise ValueError('Use a completed nominal architecture current screen')
    if not all((sanity/n).is_file() for n in ['summary.json', 'bench.cir.prn']):
        raise ValueError('Complete the nominal architecture screen before rate preparation')
    static = (sanity/'bench.cir').read_text()
    if not (re.search(r'(?im)^\.lib .* tt$', static) and
            re.search(r'(?im)^\.options device temp=25$', static)):
        raise ValueError('The isolated rate comparison requires the matched TT25 static control')
    report = observed.run(sanity)  # Completed waveform remeasurement only.
    if not (report['architecture']['metrics']['passed'] and
            report['architecture']['observations']['observed_thin_guard_passed']):
        raise ValueError('Nominal architecture DC/current screen failed')
    original = ROOT/'build/analog/receiver_rate_tt_25'
    proof = check_case(original, 'receiver_rate', (ROOT/'analog/openlvds.spice').read_bytes(), {},
        digest(ROOT/'scripts/verify_analog.py'), digest(ROOT/'requirements.json'), engine(), provenance())
    if not proof['passed']:
        raise ValueError('Original nominal rate fixture is stale or failed')
    manifest = json.loads((sanity/'manifest.json').read_text())
    paths = [sanity/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn']]
    paths += [original/n for n in ['source.spice', 'bench.cir', 'summary.json', 'bench.cir.prn', 'runner.py']]
    paths += [ROOT/'requirements.json']
    names = set(manifest['identity']['code']) | CODE
    identity = dict(sanity=str(sanity.relative_to(ROOT)), variant=manifest['identity']['architecture_variant'],
        inputs={str(p.relative_to(ROOT)): digest(p) for p in paths},
        code={n: digest(ROOT/'scripts'/n) for n in sorted(names)}, simulator_provenance=provenance(),
        numerical_policy=dict(stop_ns=60, output_step_ps=5, maximum_step_ps=1),
        scope='Nominal TT25 isolated schematic analog rate screen, original 410 MHz/250 mV differential stimulus and 100 fF load; no native digital RX, physical, channel or PHY admission')
    root = ROOT/'build/diagnostics/receiver_architecture_rate'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    source = (sanity/'source.spice').read_text()
    deck = fixture((original/'bench.cir').read_text(), static, original, root)
    ProbeNetwork(source).validate(deck, ['P', 'N', 'Q'])
    for name, text in [('source.spice', source), ('bench.cir', deck)]:
        path = root/name
        if path.exists() and path.read_text() != text:
            raise ValueError('Rate fixture changed')
        if not path.exists():
            path.write_text(text)
    capture_manifest(root/'manifest.json', dict(identity=identity, qualified_phy=False,
        files={n: digest(root/n) for n in ['source.spice', 'bench.cir']}))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_rate'):
        raise ValueError('Use a prepared isolated rate screen')
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']
    stamp = digest(root/'manifest.json')
    def unchanged():
        if (digest(root/'manifest.json') != stamp or provenance() != identity['simulator_provenance'] or
            any(digest(ROOT/n) != h for n, h in identity['inputs'].items()) or
            any(digest(ROOT/'scripts'/n) != h for n, h in identity['code'].items()) or
            any(digest(root/n) != h for n, h in manifest['files'].items())):
            raise ValueError('Architecture rate context changed')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        cached = json.loads((root/'summary.json').read_text()) if (root/'summary.json').exists() else None
        if cached is None:
            if any((root/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                raise ValueError('Partial rate screen retained; use a fresh context')
            atomic(root/'execution.json', dict(status='waiting_for_slot', qualified_phy=False))
            with lease(ROOT, priority=0, label='architecture_rate_'+identity['variant']):
                unchanged(); atomic(root/'execution.json', dict(status='running', qualified_phy=False))
                process = subprocess.run(command(root/'ngspice.log', root/'bench.cir'), cwd=root, capture_output=True, text=True)
            (root/'console.log').write_text(process.stdout+process.stderr); process.check_returncode()
        elif digest(root/'bench.cir.prn') != cached['waveform_sha256']:
            raise ValueError('Completed rate waveform changed')
        wave, headers = read_wave(root/'bench.cir.prn'); t = wave[:, 1]
        if (len(t) < 2 or t[0] > 1e-15 or t[-1] < 60e-9-1e-12 or
            np.any(np.diff(t) <= 0) or not np.isfinite(wave).all() or headers.get('V(Q)') != 4):
            raise ValueError('Incomplete or invalid full rate waveform')
        result = dict(diagnostic_complete=True, qualified_phy=False, variant=identity['variant'],
            metrics=receiver_rate_metrics(wave), manifest_sha256=stamp,
            waveform_sha256=digest(root/'bench.cir.prn'), scope=identity['scope'])
        unchanged()
        if cached is not None and cached != result:
            raise ValueError('Rate measurements differ from completed waveform')
        capture_manifest(root/'summary.json', result)
        atomic(root/'execution.json', dict(status='completed', qualified_phy=False, passed=result['metrics']['passed']))
        return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        print(json.dumps(run(a.artifact.resolve())), flush=True)
