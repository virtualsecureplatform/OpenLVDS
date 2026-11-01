#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare the original driver with the audited P64/N24, 110:1 current candidate."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path

import probe_native_driver_restore as native
from driver_current_variant import source_variant, VARIANT
from driver_restore_variant import source_variant as restored
from dll_candidate_library import audited
from spice_library import checked_netlist
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name


def physical_models(layouts):
    if set(layouts) != set(native.CASES):
        raise ValueError('Require original reference and corrected P64/N24 native models')
    source = (ROOT/'analog/openlvds.spice').read_text(); models = {}; files = []; code = {NAME, 'driver_current_variant.py'}
    for case, folder in layouts.items():
        if not folder.is_relative_to(ROOT/'build/diagnostics/driver_layout'):
            raise ValueError('Use isolated audited driver layouts')
        physical = json.loads((folder/'summary.json').read_text()); info = json.loads((folder/'extraction.json').read_text())
        corrected = case == 'restore_64_24'
        expected = source_variant(source) if corrected else restored(source, False)
        variant = VARIANT if corrected else 'source_control'
        if (not physical['passed'] or physical['identity']['variant'] != variant or
            (folder/'candidate.spice').read_text() != expected or
            native.digest(folder/'candidate.spice') != physical['source_sha256']):
            raise ValueError('Native driver differs from the declared 110:1 comparison')
        if info['ports'] != native.PORTS:
            raise ValueError('Corrected driver changes the public terminal order')
        for name, stamp in physical['files'].items():
            if native.digest(folder/name) != stamp:
                raise ValueError('Driver physical evidence changed')
        for name, stamp in physical['identity']['code'].items():
            if native.digest(ROOT/'scripts'/name) != stamp:
                raise ValueError('Driver physical producer changed')
        gds = ROOT/physical['designs'][native.TOP]['gds']
        if native.digest(gds) != info['gds_sha256'] or info['source_sha256'] != physical['source_sha256']:
            raise ValueError('Driver extraction differs from source/GDS')
        audit = audited(folder, info); models[case] = checked_netlist(info)
        files.extend(folder/n for n in ['summary.json', 'candidate.spice', 'extraction.json', 'rc_audit.json'])
        files.extend(folder/n for n in physical['files'])
        files.extend([ROOT/info['netlist'], ROOT/audit['report']]); code.update(physical['identity']['code'])
    return models, files, code


@contextmanager
def profile():
    previous = native.physical_models, native.CODE, native.slot
    try:
        native.physical_models = physical_models
        native.CODE = sorted(set(native.CODE) | {NAME, 'driver_current_variant.py', 'spice_dispatch.py'})
        native.slot = lambda: lease(ROOT, priority=1, label='driver_current_native')
        yield
    finally:
        native.physical_models, native.CODE, native.slot = previous


def prepare(parent, control, candidate):
    with profile():
        return native.prepare(parent, control, candidate)


def run(root):
    manifest = json.loads((root/'manifest.json').read_text()); identity = manifest['identity']
    if identity['code'].get(NAME) != native.digest(Path(__file__)):
        raise ValueError('Corrected-driver comparison producer changed')
    for task in manifest['tasks']:
        folder = root/task['id']
        if not (folder/'summary.json').exists() and any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
            raise ValueError('Partial native comparison retained; prepare a fresh context')
    with profile():
        # Original loaded link, 20 ps maximum step, both native cases and
        # full decoder/eye observations. No electrical or PHY promotion.
        native.run(root)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--control', type=Path); p.add_argument('--candidate', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        if a.control is None or a.candidate is None:
            p.error('--control and --candidate are required')
        print(prepare(a.artifact.resolve(), a.control.resolve(), a.candidate.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
