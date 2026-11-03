# SPDX-License-Identifier: GPL-3.0-only
"""Bounded two-inverter receive-clock duty/phase correction experiment.

The weak first NMOS delays the output rising edge; its stronger PMOS keeps
the opposite edge fast. A strong second inverter restores capture slew.
All four MOS devices are explicit SKY130 1.8 V devices, with no new bias.
"""
VERSION = 'rx-clock-skew-source-v1'
TOP = 'openlvds_rx_clock_skew_v1'
N = 'sky130_fd_pr__nfet_01v8'
P = 'sky130_fd_pr__pfet_01v8'
VARIANTS = dict(n042=.42, n065=.65, n084=.84, n100=1.)


def circuit(variant):
    if variant not in VARIANTS:
        raise ValueError('Select a declared receive-clock skew variant')
    devices = [dict(name='XP0', terminals=['MID', 'IN', 'VDDD', 'VDDD'], model=P, width_um=4., length_um=.15),
               dict(name='XN0', terminals=['MID', 'IN', 'VSS', 'VSS'], model=N, width_um=VARIANTS[variant], length_um=.15),
               dict(name='XP1', terminals=['OUT', 'MID', 'VDDD', 'VDDD'], model=P, width_um=16., length_um=.15),
               dict(name='XN1', terminals=['OUT', 'MID', 'VSS', 'VSS'], model=N, width_um=8., length_um=.15)]
    body = ['* ' + VERSION + ' ' + variant, '.subckt ' + TOP + ' IN OUT VDDD VSS']
    body += [d['name'] + ' ' + ' '.join(d['terminals']) + ' ' + d['model'] +
             f' w={d["width_um"]:g} l={d["length_um"]:g}' for d in devices]
    return '\n'.join([*body, '.ends ' + TOP, '']), devices
