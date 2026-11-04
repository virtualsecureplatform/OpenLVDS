# SPDX-License-Identifier: GPL-3.0-only
# Initial full-bank PDN experiment; native electrical admission is separate.
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections
add_global_connection -net VGND -inst_pattern {^shared_base$} -pin_pattern {^VSS$} -ground
global_connect
set_voltage_domain -name CORE -power VPWR -ground VGND
define_pdn_grid -name weighted_grid -starts_with POWER -voltage_domain CORE -pins {met4 met5}
add_pdn_stripe -grid weighted_grid -layer met4 -width 1.6 -pitch 8.0 -spacing 1.6 -offset 1.0 -starts_with POWER
add_pdn_stripe -grid weighted_grid -layer met5 -width 1.6 -pitch 13.0 -spacing 1.6 -offset 6.58 -starts_with POWER
add_pdn_stripe -grid weighted_grid -layer met1 -width 0.48 -followpins
add_pdn_connect -grid weighted_grid -layers {met1 met4}
add_pdn_connect -grid weighted_grid -layers {met4 met5}
# Guarded pair rails are horizontal M4; escape locally on M5 rather
# than relying on unrelated chip-wide horizontal stripe phases.
define_pdn_grid -macro -name guarded_pair_grid -cells {openlvds_nand2b_4_o1_stack_guard_pair_v2} -grid_over_boundary -starts_with GROUND -halo {4.0 0.2} -obstructions {met5}
add_pdn_stripe -grid guarded_pair_grid -layer met5 -width 1.6 -pitch 100.0 -spacing 2.8 -offset 3.7 -starts_with GROUND -extend_to_boundary
add_pdn_connect -grid guarded_pair_grid -layers {met3 met5}
add_pdn_connect -grid guarded_pair_grid -layers {met4 met5}
define_pdn_grid -macro -default -name weighted_macros -starts_with POWER -halo {0.2 0.2}
add_pdn_connect -grid weighted_macros -layers {met3 met4}
add_pdn_connect -grid weighted_macros -layers {met4 met5}
