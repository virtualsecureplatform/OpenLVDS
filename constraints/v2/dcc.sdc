# SPDX-License-Identifier: GPL-3.0-only
# Asynchronous pulse/toggle island. Native extracted simulation must establish
# pulse widths, event integrity and half-cycle timing; this is no STA closure.
set_false_path -from [all_inputs] -to [all_outputs]
set_false_path -from [get_pins -hierarchical */Q] -to [get_pins -hierarchical */RESET_B]
set_load 0.020 [all_outputs]
