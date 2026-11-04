# SPDX-License-Identifier: GPL-3.0-only
# Calibrated asynchronous delay bank: native transient characterization admits
# delay codes. STA must not resize or replace the fixed physical delay paths.
set_false_path -from [all_inputs] -to [all_outputs]
set_load 0.030 [get_ports OUT]
