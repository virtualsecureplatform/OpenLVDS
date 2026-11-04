# SPDX-License-Identifier: GPL-3.0-only
"""One physical fine-bank unit, including its complementary-control shunt.

The node-wide shunt and digital control inverter are outside this unit. This
five-port primitive is used by both the DCDL bank and threshold-branch layouts;
its geometry alone cannot transfer electrical or PHY qualification.
"""
NAME='openlvds_mim_switch_unit_v2'
VERSION='mim-switch-with-control-shunt-unit-v2.1'
N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'
CAP='sky130_fd_pr__cap_mim_m3_1'


def schematic():
    return (f'.subckt {NAME} NODE EN ENB VDD VSS\n'
        f'XSWN NODE EN CAP VSS {N} w=0.42 l=0.15\n'
        f'XSWP CAP ENB NODE VDD {P} w=0.84 l=0.15\n'
        f'XCLR CAP ENB VSS VSS {N} w=0.42 l=0.15\n'
        f'XCUNIT CAP VSS {CAP} w=2 l=2\n'
        f'XCCTRL ENB VSS {CAP} w=2 l=2\n'
        f'.ends {NAME}\n')
