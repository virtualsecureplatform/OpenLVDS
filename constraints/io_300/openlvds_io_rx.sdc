# SPDX-License-Identifier: GPL-3.0-only
# Template for the logic sampling openlvds_io_rx. Replace <clk>, <period> and
# <instance>. The Liberty INP->Q arc is measured from the differential zero
# crossing at the macro pins; add your pad, package and board delay to the
# input delay. Q is asynchronous to any local clock unless the link is
# source-synchronous: sample it through a synchronizer or a forwarded clock.
# create_clock -name <clk> -period <period> [get_ports <clk>]
# set_input_delay <arrival> -clock <clk> [get_pins <instance>/INP]
# set_max_delay <budget> -from [get_pins <instance>/Q]
# INP, INN, VREF and IREF are analog pins: route them by hand, not as timed nets.
