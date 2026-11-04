# SPDX-License-Identifier: GPL-3.0-only
# Align chip-wide M5 rails to the native guarded-pair PG centers.
# Ground Y=13.5+28.6*n; power Y=17.9+28.6*n, core bottom Y=2.72.
# Native electrical admission and whole-bank signoff remain separate.
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections
add_global_connection -net VGND -inst_pattern {^shared_base$} -pin_pattern {^VSS$} -ground
global_connect
set_voltage_domain -name CORE -power VPWR -ground VGND
define_pdn_grid -name weighted_grid -starts_with POWER -voltage_domain CORE -pins {met4 met5}
add_pdn_stripe -grid weighted_grid -layer met4 -width 1.6 -pitch 8.0 -spacing 1.6 -offset 1.0 -starts_with POWER
add_pdn_stripe -grid weighted_grid -layer met5 -width 1.6 -pitch 28.6 -spacing 2.8 -offset 10.78 -starts_with GROUND
# Supply the retained bottom boundary row below the first guarded bank row.
add_pdn_stripe -grid weighted_grid -layer met5 -width 1.6 -pitch 1000.0 -offset 2.28 -nets {VPWR} -starts_with POWER
add_pdn_stripe -grid weighted_grid -layer met1 -width 0.48 -followpins
add_pdn_connect -grid weighted_grid -layers {met1 met4}
add_pdn_connect -grid weighted_grid -layers {met4 met5}
define_pdn_grid -macro -default -name weighted_macros -starts_with POWER -halo {0.2 0.2}
add_pdn_connect -grid weighted_macros -layers {met3 met4}
add_pdn_connect -grid weighted_macros -layers {met4 met5}
