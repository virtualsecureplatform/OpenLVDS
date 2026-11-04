# SPDX-License-Identifier: GPL-3.0-only
"""The shared node shunt retained by the measured DCDL source core."""
NAME='openlvds_mim_base_4x4_v2'
VERSION='dcdl-shared-node-native-mim-4x4-v2.1'


def schematic():
    return (f'.subckt {NAME} NODE VSS\n'
        'XCBASE NODE VSS sky130_fd_pr__cap_mim_m3_1 w=4 l=4\n'
        f'.ends {NAME}\n')
