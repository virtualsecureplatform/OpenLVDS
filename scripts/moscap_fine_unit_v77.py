# SPDX-License-Identifier: GPL-3.0-only
"""Native physical schematic for the complementary gate-cap fine quantum.

This is a new physical cell. Junctions must come from its own extraction;
the component prototype's old switch junctions are not physical constraints.
"""
WIDTHS = dict(w042='.42', w084='.84', w126='1.26')
N = 'sky130_fd_pr__nfet_01v8'
P = 'sky130_fd_pr__pfet_01v8'
MIM = 'sky130_fd_pr__cap_mim_m3_1'


def name(profile):
    if profile not in WIDTHS:
        raise ValueError('Unknown gate-cap fine quantum')
    return 'openlvds_moscap_fine_' + profile + '_v77'


def schematic(profile):
    top = name(profile)
    w = WIDTHS[profile]
    return (f'.subckt {top} NODE EN ENB VDD VSS\n'
            f'XSWN NODE EN CAP VSS {N} w=.42 l=.15\n'
            f'XSWP CAP ENB NODE VDD {P} w=.84 l=.15\n'
            f'XCLR CAP ENB VSS VSS {N} w=.42 l=.15\n'
            f'XGCN VSS CAP VSS VSS {N} w={w} l=.15\n'
            f'XGCP VDD CAP VDD VDD {P} w={w} l=.15\n'
            f'XGUARD ENB VSS {MIM} w=2 l=2\n'
            f'.ends {top}\n')
