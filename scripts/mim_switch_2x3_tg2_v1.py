# SPDX-License-Identifier: GPL-3.0-only
"""Controlled TG-strength experiment; retain both original MIM areas and clamp.

The original 2x3 unit and its extracted model remain unchanged. This distinct
macro needs its own native geometry, DRC/LVS, extraction and electrical proofs.
"""
NAME='openlvds_mim_switch_2x3_tg2_v1'
VERSION='mim-switch-2x3-double-transmission-gate-v1'
N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'
CAP='sky130_fd_pr__cap_mim_m3_1'


def schematic():
    return (f'.subckt {NAME} NODE EN ENB VDD VSS\n'
        f'XSWN NODE EN CAP VSS {N} w=0.84 l=0.15\n'
        f'XSWP CAP ENB NODE VDD {P} w=1.68 l=0.15\n'
        f'XCLR CAP ENB VSS VSS {N} w=0.42 l=0.15\n'
        f'XCUNIT CAP VSS {CAP} w=2 l=3\n'
        f'XCCTRL ENB VSS {CAP} w=2 l=2\n'
        f'.ends {NAME}\n')
