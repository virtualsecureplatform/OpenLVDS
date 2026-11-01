#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Add only internal voltage observations to the fixed iteration-budget RX control."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import re

import replay_selected_receiver_iterations as iteration
from dll_campaign import text_block
from exact_rc_candidate import parse
from receiver_static_diagnosis import capture_manifest
from spice_probes import ProbeNetwork

replay = iteration.replay
NAME = Path(__file__).name
LEAVES = ['rise_enable.A', 'held_rise.D', 'held_rise.Q', 'fall_enable.A',
          'fall_enable.B', 'falling_clock.Y', 'serial', 'clk']


def aliases(library):
    # Observe every retained fragment of known capture/publication nets,
    # rather than choosing a convenient bus or only one device terminal.
    network = parse(text_block(library, 'openlvds_ddr_rx'))
    nodes = set(network['graph']) | network['protected']; result = []
    for leaf in LEAVES:
        matching = sorted(n for n in nodes if n == leaf or re.fullmatch(re.escape(leaf)+r'\.(?:t|n)\d+', n))
        if not matching:
            raise ValueError('Missing retained native capture observation '+leaf)
        # ngspice exports these two public ports under their parent names
        # RXDATA/RXCLOCK, which the original nine vectors already include.
        # Retain all internal RC fragments, but avoid duplicate port aliases
        # that the strict raw-to-table exporter cannot name independently.
        result.extend('XRX:'+n for n in matching if not (leaf in ['serial', 'clk'] and n == leaf))
    result.extend(instance+':openlvds_receiver_core__'+leaf
        for instance in ['XDR', 'XCR'] for leaf in ['PP', 'PN', 'CO', 'CL', 'CT', 'NBC', 'RESTORE0', 'RESTORE1'])
    return result


def add_probes(deck, nodes):
    matches = list(re.finditer(r'(?im)^\.print tran[^\n]*$', deck))
    if len(matches) != 1:
        raise ValueError('Expected exactly one physical replay print statement')
    at = matches[0].end()
    return deck[:at]+' '+' '.join('V('+n+')' for n in nodes)+deck[at:]


@contextmanager
def profile(parent):
    library, _ = iteration.exact.reduce_library((parent/'library.spice').read_text())
    nodes = aliases(library)
    ProbeNetwork(library).validate((parent/'bench.cir').read_text(), nodes)
    with iteration.profile(parent) as reference:
        previous = replay.fixture, replay.CODE
        try:
            original = replay.fixture
            replay.fixture = lambda *a, **kw: add_probes(original(*a, **kw), nodes)
            replay.CODE = set(replay.CODE) | {NAME}
            yield reference, nodes
        finally:
            replay.fixture, replay.CODE = previous


def certify(root, reference, headers, nodes):
    # The scientific replay still analyzes its original public vectors;
    # the native .prn/raw retains all extra columns for separate diagnosis.
    ProbeNetwork((root/'library.spice').read_text()).validate((root/'bench.cir').read_text(), nodes)
    iteration.exact.certify(root, reference, headers)
    certificate = dict(producer_sha256=replay.digest(Path(__file__)), aliases=nodes,
        manifest_sha256=replay.digest(root/'manifest.json'),
        deck_sha256=replay.digest(root/'bench.cir'), library_sha256=replay.digest(root/'library.spice'),
        physical_or_numerical_intervention=False, qualified_phy=False,
        scope='Internal voltage observations only. Same bounded input pins, exact resistor-only circuit, 5 ps maximum step and itl4=100. Incomplete observations cannot prove electrical failure or PHY admission.')
    capture_manifest(root/'internal_observation_certificate.json', certificate)


def prepare(parent, sanity):
    with profile(parent) as ((reference, headers), nodes):
        root = replay.prepare(parent, sanity)
        if json.loads((root/'manifest.json').read_text())['identity']['variant'] != 'lvt':
            raise ValueError('This observation context is the original LVT control only')
        certify(root, reference, headers, nodes)
    return root


def run(root, wait_slot=None):
    identity = json.loads((root/'manifest.json').read_text())['identity']
    if identity['variant'] != 'lvt' or identity['code'].get(NAME) != replay.digest(Path(__file__)):
        raise ValueError('Internal receiver observation producer or control changed')
    parent = replay.ROOT/identity['parent']
    with profile(parent) as ((reference, headers), nodes):
        certify(root, reference, headers, nodes)
        report = replay.run(root, wait_slot)
        certify(root, reference, headers, nodes)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--sanity', type=Path)
    p.add_argument('--wait-slot', type=int, choices=range(6)); a = p.parse_args()
    if a.action == 'prepare':
        if a.sanity is None:
            p.error('--sanity is required')
        print(prepare(a.artifact.resolve(), a.sanity.resolve()), flush=True)
    else:
        run(a.artifact.resolve(), a.wait_slot)
