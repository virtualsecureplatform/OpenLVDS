# SPDX-License-Identifier: GPL-3.0-only
# Template for the logic driving openlvds_io_tx. Replace <clk>, <period> and
# <instance>. The macro is asynchronous: D has no setup or hold check, so the
# launch flop's clock-to-D delay adds directly to the transmitted edge.
# Keep the D net short and its 20-80% transition below the Liberty
# max_transition; D load is the Liberty input capacitance.
# create_clock -name <clk> -period <period> [get_ports <clk>]
# set_max_delay <budget> -to [get_pins <instance>/D]
# set_max_transition 0.5 [get_pins <instance>/D]
# OUTP, OUTN, VREF and IREF are analog pins: route them by hand, not as timed nets.
