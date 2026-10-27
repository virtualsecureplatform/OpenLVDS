# SPDX-License-Identifier: GPL-3.0-only
# Asynchronous PFD: pulse width, polarity, and reset behavior are qualified in
# transistor simulation. There is no synchronous data path to false-close.
set_false_path -from [all_inputs] -to [all_outputs]
set_false_path -from [get_pins -hierarchical */Q] -to [get_pins -hierarchical */RESET_B]
set_load 0.020 [all_outputs]
