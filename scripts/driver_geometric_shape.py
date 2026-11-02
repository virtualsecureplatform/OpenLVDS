# SPDX-License-Identifier: GPL-3.0-only
"""One calculated source candidate: near-geometric 1/3/8 taper and 36 um MIMs."""
from dll_campaign import text_block
from spice_library import replace
import driver_gate_taper as taper
import probe_driver_gate_taper as measurement

OLD = taper.SHIFT + '_taper_16_64_128'
NEW = taper.SHIFT + '_taper_16_48_128_shape36'
COUNTS = (1, 3, 8)
POINTS = [('tt', 25), ('ss', 25), ('ff', 40)]


def transform(source):
    top = text_block(source, taper.TOP)
    line = 'XLS D DP DN NB VDDIO VDDD VSS ' + OLD
    if top.splitlines().count(line) != 1:
        raise ValueError('Require the completed 1/4/8-cap30 reference')
    block = text_block(source, OLD)
    for branch in [0, 1]:
        for stage, count in enumerate([1, 4, 8]):
            if len([s for s in block.splitlines() if s.startswith(f'XB{branch}_S{stage}_')]) != count:
                raise ValueError('Original gate-stage counts changed')
        old = f'XB{branch}_S1_3 G{branch}_0 G{branch}_1 VDDIO VSS {taper.UNIT}'
        if block.splitlines().count(old) != 1:
            raise ValueError('Original intermediate-stage unit changed')
        block = block.replace(old + '\n', '')
    for name, pin in [('XCOUTP', 'OUTP'), ('XCOUTN', 'OUTN')]:
        old = f'{name} {pin} VSS sky130_fd_pr__cap_mim_m3_1 w=30 l=30'
        if top.splitlines().count(old) != 1:
            raise ValueError('Require the original symmetric 30 um caps')
        top = top.replace(old, old.replace('w=30 l=30', 'w=36 l=36'))
    source = replace(source, taper.TOP, top.replace(OLD, NEW))
    return replace(source, OLD, block.replace(OLD, NEW))


def measure(folder):
    result = measurement.measure(folder, 'taper_16_64_128')
    wave, headers = measurement.read_wave(folder / 'bench.cir.prn')
    result['added_mos_stress'] = measurement.added_stress(wave, headers, COUNTS)
    result['scope'] = 'Calculated 1/3/8-cap36 source candidate; actual rail currents and 1/3/8 device counts, without physical or PHY admission.'
    return result
