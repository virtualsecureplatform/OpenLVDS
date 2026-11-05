# SPDX-License-Identifier: GPL-3.0-only
# Temporary routing types are restored before saving the final database.
read_db @PARENT@/placed.odb
proc snapshot_master_pins {path} {
  set f [open $path w]
  foreach lib [[ord::get_db] getLibs] {foreach master [$lib getMasters] {foreach term [$master getMTerms] {
    foreach pin [$term getMPins] {foreach box [$pin getGeometry] {
      puts $f "[$master getName]\t[$term getName]\t[$term getIoType]\t[$term getSigType]\t[[$box getTechLayer] getName]\t[$box xMin]\t[$box yMin]\t[$box xMax]\t[$box yMax]"
    }}
  }}}
  close $f
}
snapshot_master_pins {@OUT@/master_pins_before.tsv}
set block [ord::get_db_block]
[$block findNet IN] setSpecial
set db [ord::get_db]
set pg_terms {}
foreach lib [$db getLibs] {foreach master [$lib getMasters] {foreach term [$master getMTerms] {
  set type [$term getSigType]
  if {$type == "POWER" || $type == "GROUND"} {lappend pg_terms [list $term $type]; $term setSigType SIGNAL}
}}}
set out_net [$block findNet OUT]
$out_net setSpecial
set disconnected {}
foreach inst [$block getInsts] {
  foreach term [$inst getITerms] {
    set routing 0
    foreach pin [[$term getMTerm] getMPins] {foreach shape [$pin getGeometry] {if {[[$shape getTechLayer] getRoutingLevel] > 0} {set routing 1}}}
    if {!$routing} {lappend disconnected [list $term [$term getNet]]; $term disconnect}
  }
}
foreach name {VPWR VGND} {
  set net [$block findNet $name]
  if {[llength [$net getSWires]] != 1} {error "Unexpected fixed supply-wire inventory"}
  foreach wire [$net getSWires] {odb::dbSWire_destroy $wire}
  $net setSigType SIGNAL
  foreach term [$net getBTerms] {$term setSigType SIGNAL; $term setIoType INPUT}
}
make_tracks
set_routing_layers -signal met1-met5 -clock met1-met5
set_global_routing_layer_adjustment met1-met5 0.3
global_route -guide_file @OUT@/route.guide -allow_congestion -verbose
write_db @OUT@/global.odb
detailed_route -output_drc @OUT@/route.drc
foreach pair $disconnected {lassign $pair term net; $term connect $net}
foreach name {VPWR VGND} {
  set net [$block findNet $name]
  set type [expr {$name == "VPWR" ? "POWER" : "GROUND"}]
  $net setSigType $type
  foreach term [$net getBTerms] {$term setSigType $type; $term setIoType INOUT}
}
foreach pair $pg_terms {lassign $pair term type; $term setSigType $type}
snapshot_master_pins {@OUT@/master_pins_after.tsv}
@RESTORE_POWER@
foreach net [$block getNets] {if {[$net getWire] == "NULL"} {puts "NO_REGULAR_WIRE [$net getName]"}}
check_placement -verbose
set f [open {@OUT@/connections.tsv} w]
set g [open {@OUT@/boxes.tsv} w]
foreach inst [$block getInsts] {
  set b [$inst getBBox]
  puts $g "[$inst getName]\t[[$inst getMaster] getName]\t[$inst getOrient]\t[$inst getPlacementStatus]\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"
  foreach term [$inst getITerms] {
    set net [$term getNet]
    if {$net == "NULL"} {error "Unconnected native terminal after routing"}
    puts $f "[$inst getName]\t[[$term getMTerm] getName]\t[$net getName]"
  }
}
close $f
close $g
set f [open {@OUT@/ports.tsv} w]
foreach term [$block getBTerms] {puts $f "[$term getName]\t[$term getIoType]\t[$term getSigType]\t[[$term getNet] getName]"}
close $f
set f [open {@OUT@/nets.tsv} w]
foreach net [$block getNets] {puts $f "[$net getName]\t[$net getSigType]\t[expr {[$net getWire] != "NULL"}]\t[llength [$net getSWires]]"}
close $f
write_db @OUT@/routed.odb
write_def @OUT@/routed.def
exit
