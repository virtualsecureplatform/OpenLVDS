# SPDX-License-Identifier: GPL-3.0-only
# 420 MHz stress case. Uncertainty includes duty distortion and injected jitter.
create_clock -name clk_400 -period 2.380952 [get_ports clk_400]
create_clock -name clk_90 -period 2.380952 -waveform {0.595238 1.785714} [get_ports clk_90]
set_clock_uncertainty 0.200 [all_clocks]
set_clock_transition 0.100 [all_clocks]
# Propagated local clocks also need an explicit port slew.
set_input_transition 0.100 [all_inputs]
set_input_delay 0.250 -clock clk_400 [get_ports {tx_data*}]
set_output_delay 0.000 -clock clk_90 [get_ports tx_serial]
set_output_delay 0.000 -clock clk_400 [get_ports forwarded_clock]
# Both outputs drive analog drivers; neither is captured on the next input
# clock edge. Bound launch latency directly and verify their DIFFERENTIAL
# phase/skew in the extracted source-synchronous link bench.
# OpenSTA subtracts the 0.200 ns uncertainty from this constraint, leaving
# an effective 1.100 ns launch-latency allowance including the clock tree.
set_max_delay 1.300 -from [all_clocks] -to [get_ports {tx_serial forwarded_clock}]
set_load 0.080 [get_ports {tx_serial forwarded_clock}]
# These are static bring-up controls. No data or opposite-edge paths are waived.
set_false_path -from [get_ports {reset_n enable clock_ready dll_locked}]
set_false_path -to [get_ports tx_ready]
