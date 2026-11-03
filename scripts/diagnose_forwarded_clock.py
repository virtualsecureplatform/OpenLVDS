#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Decompose the forwarded clock against its actual steady-state mux function.

The TX mux emits ~CLK0 after its constant 10 pair has been captured using
CLK90. Comparing its pulse width to CLK90 includes an intentional inversion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np

import diagnose_compensated_clock as original
from digital_candidate_rc import captured_inputs
from physical_policy import tx_buffered_paths_retained
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = original.sha


def clock_function(netlist):
    if not tx_buffered_paths_retained(netlist, 4):
        raise ValueError('Require the retained buffered TX topology')
    cells = {name.lstrip('\\'): (cell, dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)', body)))
        for cell, name, body in re.findall(r'\b(sky130_fd_sc_hd__\w+)\s+(\\?\S+)\s*\((.*?)\);', netlist, re.S)}
    def pins(name, cell):
        kind, ports = cells['clock_launch/' + name]
        if kind != 'sky130_fd_sc_hd__' + cell:
            raise ValueError('Forwarded-clock cell type changed')
        return ports
    select = pins('select_clock', 'buf_4'); mux = pins('output_logic', 'mux2_4')
    rise = pins('rise_sample', 'dfrtp_4'); held = pins('held_sample', 'dfrtp_4')
    fall = pins('fall_sample', 'dfrtp_4'); invert = pins('falling_clock', 'inv_4')
    ties = {(cell, pin, node) for cell, ports in cells.values() for pin, node in ports.items()
            if cell == 'sky130_fd_sc_hd__conb_1'}
    if not (select['A'] == 'clk_400' and select['X'] == mux['S']
            and rise['CLK'] == held['CLK'] == invert['A'] == 'clk_90'
            and fall['CLK'] == invert['Y'] and fall['D'] == held['Q']
            and mux['A0'] == fall['Q'] and mux['A1'] == rise['Q']
            and ('sky130_fd_sc_hd__conb_1', 'LO', rise['D']) in ties
            and ('sky130_fd_sc_hd__conb_1', 'HI', held['D']) in ties):
        raise ValueError('Forwarded-clock select, phase, data or polarity changed')
    return dict(steady_function='forwarded_clock = ~clk_400', capture_clock='clk_90',
        constant_pair='10', mux_select='clk_400', selected_high_bit=0, selected_low_bit=1)


def topology(parent):
    m = json.loads((parent / 'manifest.json').read_text())
    proofs = [ROOT / n for n in m['identity']['inputs'] if n.startswith('build/diagnostics/tx_exact_current_witness/') and n.endswith('/summary.json')]
    if len(proofs) != 1:
        raise ValueError('Require the exact selected TX physical witness')
    proof = json.loads(proofs[0].read_text()); physical = ROOT / proof['identity']['physical']
    manifest = json.loads((physical / 'summary.json').read_text())
    if captured_inputs(physical, manifest) != 'openlvds_tx_core':
        raise ValueError('Wrong physical TX context')
    netlist = ROOT / manifest['run'] / 'final/nl/openlvds_tx_core.nl.v'
    function = clock_function(netlist.read_text())
    archive = ROOT / manifest['input_archive']
    paths = [proofs[0], physical / 'summary.json', physical / 'config.json', netlist]
    paths += sorted(p for p in archive.iterdir() if p.is_file())
    return function, {str(p.relative_to(ROOT)): sha(p) for p in paths}


def analyze(wave, header):
    t = wave[:, 1]; v = lambda n: wave[:, header['V(' + n + ')']]
    if t[0] > 0 or t[-1] < 120e-9 or not np.isfinite(wave).all():
        raise ValueError('Incomplete forwarded-clock observation interval')
    signals = [('intended_inverted_clk0', 1.8 - v('CLK0'), .9), ('tx_digital', v('TXCLOCK'), .9),
        ('tx_differential', v('CP') - v('CN'), 0), ('rx_differential', v('RCP') - v('RCN'), 0),
        ('rx_digital', v('RXCLOCK'), .9)]
    stages = {name: original.stage(t, signal, level, 60e-9, 120e-9) for name, signal, level in signals}
    propagation = {first + '_to_' + last: original.transport(t, source, sl, target, tl, 60e-9, 120e-9)
        for (first, source, sl), (last, target, tl) in zip(signals[:-1], signals[1:])}
    return dict(stages=stages, propagation=propagation, interval_ns=[60, 120],
        capture_clock_quadrature=original.stage(t, v('CLK90'), .9, 60e-9, 120e-9))


def diagnose(parent):
    if original.coupled.verify(parent).get('payload_restored') is not True:
        raise ValueError('Require independently verified restored payload')
    function, inputs = topology(parent)
    wave, header = original.coupled.baseline.completed_export(parent / 'payload', 188.049)
    result = analyze(wave, header)
    paths = [parent / 'manifest.json', parent / 'summary.json', parent / 'payload/summary.json']
    paths += [parent / 'payload' / n for n in ('bench.cir', 'library.spice', 'bench.raw', 'bench.cir.prn')]
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs=inputs, code={n: sha(ROOT / 'scripts' / n)
        for n in (Path(__file__).name, 'diagnose_compensated_clock.py', 'digital_candidate_rc.py',
                  'physical_policy.py', 'simulate_link.py', 'restore_compensated_coupled.py')})
    out = ROOT / 'build/diagnostics/forwarded_clock_stages' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'summary.json', dict(identity=identity, topology=function, **result, qualified_phy=False,
        supersedes_interpretation='compensated_clock_stages/31040a7b95cd8515 compared CLK90 to the output, '
            'including intentional clock inversion and phase relationships. Its first hop is not TX-added duty distortion.',
        scope='Read-only steady-state timing diagnosis. The mapped, source-bound clock mux selects registered 0/1 '
              'with CLK0, so ~CLK0 is the reference. Digital 0.9 V and differential zero crossings only. '
              'No startup/control, aperture, loop, corrected-clock circuit or PHY admission.'))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    print(diagnose(p.parse_args().artifact.resolve()), flush=True)
