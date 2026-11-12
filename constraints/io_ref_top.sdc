# SPDX-License-Identifier: GPL-3.0-only
# Reference integration only: one relaxed clock for the generator and checker.
create_clock -name clk -period 10.0 [get_ports clk]
set_clock_uncertainty 0.2 [get_clocks clk]
set_input_delay 2.0 -clock clk [get_ports {enable}]
set_output_delay 2.0 -clock clk [get_ports {checker_locked checker_error}]
set_false_path -from [get_ports reset_n]
# Differential, reference and bias pins are analog nets, not timing endpoints.
set_false_path -from [get_ports {rx_p rx_n}]
