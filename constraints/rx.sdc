# SPDX-License-Identifier: GPL-3.0-only
create_clock -name rx_clk -period 2.380952 [get_ports clk]
set_clock_transition 0.100 [all_clocks]
set_clock_uncertainty 0.200 [all_clocks]
# Data transitions halfway BETWEEN sampling edges, not at the sampling edges.
# A virtual DDR launch clock models the centered forwarded-clock interface.
create_clock -name data_launch -period 2.380952 -waveform {0.595238 1.785714}
set_input_delay -max 0.100 -clock data_launch [get_ports serial]
set_input_delay -min -0.100 -clock data_launch [get_ports serial]
set_input_delay -max 0.100 -clock data_launch -clock_fall -add_delay [get_ports serial]
set_input_delay -min -0.100 -clock data_launch -clock_fall -add_delay [get_ports serial]
set_output_delay 0.250 -clock rx_clk [get_ports {data* valid}]
set_load 0.020 [get_ports {data* valid}]
set_false_path -from [get_ports reset_n]
