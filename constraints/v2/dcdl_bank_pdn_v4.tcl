# SPDX-License-Identifier: GPL-3.0-only
# Dense upper-metal grid for many small macros with M3 power access rails.
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections
add_global_connection -net VGND -inst_pattern {^shared_base$} -pin_pattern {^VSS$} -ground
global_connect
set_voltage_domain -name CORE -power VPWR -ground VGND
define_pdn_grid -name bank_grid -starts_with POWER -voltage_domain CORE -pins {met4 met5}
add_pdn_stripe -grid bank_grid -layer met4 -width 1.6 -pitch 6.0 -spacing 1.0 -offset 1.0 -starts_with POWER
add_pdn_stripe -grid bank_grid -layer met5 -width 1.6 -pitch 6.4 -spacing 1.6 -offset 0.4 -starts_with POWER
add_pdn_stripe -grid bank_grid -layer met1 -width 0.48 -followpins
add_pdn_connect -grid bank_grid -layers {met1 met4}
add_pdn_connect -grid bank_grid -layers {met4 met5}
define_pdn_grid -macro -default -name bank_macros -starts_with POWER -halo {0.2 0.2}
add_pdn_connect -grid bank_macros -layers {met3 met4}
