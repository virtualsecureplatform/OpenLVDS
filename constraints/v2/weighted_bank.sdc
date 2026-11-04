# SPDX-License-Identifier: GPL-3.0-only
# Fixed delay paths are characterized with native transient simulation.
set_false_path -from [all_inputs] -to [all_outputs]
set_load 0.020 [get_ports OUT]
