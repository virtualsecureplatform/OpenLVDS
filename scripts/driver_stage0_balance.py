# SPDX-License-Identifier: GPL-3.0-only
"""One causal sizing change: 1/4/8 to 2/4/8 gate units, preserving output caps."""
from dll_campaign import text_block
from spice_library import replace
import driver_gate_taper as taper
import probe_driver_gate_taper as measurement

OLD = taper.SHIFT + '_taper_16_64_128'
NEW = taper.SHIFT + '_taper_32_64_128'
COUNTS = (2, 4, 8)


def transform(source):
    top = text_block(source, taper.TOP)
    for name, pin in [('XCOUTP', 'OUTP'), ('XCOUTN', 'OUTN')]:
        if top.splitlines().count(f'{name} {pin} VSS sky130_fd_pr__cap_mim_m3_1 w=30 l=30') != 1:
            raise ValueError('Retain the two original 30 um capacitors')
    if top.splitlines().count('XLS D DP DN NB VDDIO VDDD VSS ' + OLD) != 1:
        raise ValueError('Require the original stronger taper binding')
    block = text_block(source, OLD)
    for branch, inn in [(0, 'L'), (1, 'R')]:
        line = f'XB{branch}_S0_0 {inn} G{branch}_0 VDDIO VSS {taper.UNIT}'
        if block.splitlines().count(line) != 1 or f'XB{branch}_S0_1 ' in block:
            raise ValueError('Require one original first-stage unit per branch')
        block = block.replace(line, line + '\n' + line.replace('_S0_0 ', '_S0_1 '))
    source = replace(source, taper.TOP, top.replace(OLD, NEW))
    return replace(source, OLD, block.replace(OLD, NEW))


def measure(folder):
    # The same three internal stage nodes exist. Only the first stage's
    # parallel-unit metadata changes; actual power uses saved rail currents.
    result = measurement.measure(folder, 'taper_16_64_128')
    wave, headers = measurement.read_wave(folder / 'bench.cir.prn')
    result['added_mos_stress'] = measurement.added_stress(wave, headers, COUNTS)
    result['scope'] = 'Source 2/4/8 stage-zero control; actual supply currents and added-device voltages, not PHY admission.'
    return result
