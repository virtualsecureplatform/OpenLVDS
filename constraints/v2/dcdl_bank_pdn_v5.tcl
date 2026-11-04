# SPDX-License-Identifier: GPL-3.0-only
# M5 power pairs follow the 13 um fine-macro rows, leaving signal corridors.
# With core Y=2.72 um, POWER centers are 9.30 + 13*k um; fine VDD is 22.30 + 13*k.
# M4 tracks retain full via4 landing width and reach all fixed macro PG rails.
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections
add_global_connection -net VGND -inst_pattern {^shared_base$} -pin_pattern {^VSS$} -ground
global_connect
set_voltage_domain -name CORE -power VPWR -ground VGND
define_pdn_grid -name bank_grid -starts_with POWER -voltage_domain CORE -pins {met4 met5}
add_pdn_stripe -grid bank_grid -layer met4 -width 1.6 -pitch 8.0 -spacing 1.6 -offset 1.0 -starts_with POWER
add_pdn_stripe -grid bank_grid -layer met5 -width 1.6 -pitch 13.0 -spacing 1.6 -offset 6.58 -starts_with POWER
add_pdn_stripe -grid bank_grid -layer met1 -width 0.48 -followpins
add_pdn_connect -grid bank_grid -layers {met1 met4}
add_pdn_connect -grid bank_grid -layers {met4 met5}
define_pdn_grid -macro -default -name bank_macros -starts_with POWER -halo {0.2 0.2}
add_pdn_connect -grid bank_macros -layers {met3 met4}
