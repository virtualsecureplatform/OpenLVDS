# SPDX-License-Identifier: GPL-3.0-only
# Diagnostic island constraints at 310 MHz. Native transient remains required
# for the event/reset feedback paths. No broad input/output timing exception.
create_clock -name phase0 -period 3.225806 -waveform {0 1.612903} [get_ports phase0]
create_clock -name phase180 -period 3.225806 -waveform {1.612903 3.225806} [get_ports phase180]
set_false_path -from [get_ports reset_n]
set_load 0.020 [get_ports clock_out]
