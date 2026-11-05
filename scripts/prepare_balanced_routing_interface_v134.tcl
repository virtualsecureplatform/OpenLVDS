# SPDX-License-Identifier: GPL-3.0-only
# Exact existing fixed metal is represented as temporary router pins.
read_db @PARENT@/placed.odb
set db [ord::get_db]
set block [ord::get_db_block]
proc snapshot {prefix} {
  global db block
  foreach kind {connections ports boxes masters nets buses} {set files($kind) [open "${prefix}_${kind}.tsv" w]}
  foreach inst [$block getInsts] {
    set b [$inst getBBox]
    puts $files(boxes) "[$inst getName]\t[[$inst getMaster] getName]\t[$inst getOrient]\t[$inst getPlacementStatus]\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"
    foreach term [$inst getITerms] {
      set net [$term getNet]
      set name NULL
      if {$net != "NULL"} {set name [$net getName]}
      puts $files(connections) "[$inst getName]\t[[$term getMTerm] getName]\t$name"
    }
  }
  foreach term [$block getBTerms] {
    puts $files(ports) "[$term getName]\t[$term getIoType]\t[$term getSigType]\t[[$term getNet] getName]"
    foreach pin [$term getBPins] {foreach b [$pin getBoxes] {
      puts $files(boxes) "PORT\t[$term getName]\t[$pin getPlacementStatus]\t[[$b getTechLayer] getName]\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"
    }}
  }
  foreach lib [$db getLibs] {foreach master [$lib getMasters] {foreach term [$master getMTerms] {
    foreach pin [$term getMPins] {foreach b [$pin getGeometry] {
      puts $files(masters) "[$master getName]\t[$term getName]\t[$term getIoType]\t[$term getSigType]\t[[$b getTechLayer] getName]\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"
    }}
  }}}
  foreach net [$block getNets] {
    puts $files(nets) "[$net getName]\t[$net getSigType]\t[$net isSpecial]\t[expr {[$net getWire] != "NULL"}]\t[llength [$net getSWires]]"
    foreach wire [$net getSWires] {foreach b [$wire getWires] {
      if {[$b isVia]} {error "Unexpected via in fixed bus"}
      puts $files(buses) "[$net getName]\t[[$b getTechLayer] getName]\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"
    }}
  }
  foreach kind [array names files] {close $files($kind)}
}
snapshot {@OUT@/before}
set disconnected {}
set f [open {@OUT@/terminal_routing.tsv} w]
foreach inst [$block getInsts] {foreach term [$inst getITerms] {
  set routing 0
  foreach pin [[$term getMTerm] getMPins] {foreach shape [$pin getGeometry] {
    if {[[$shape getTechLayer] getRoutingLevel] > 0} {set routing 1}
  }}
  puts $f "[$inst getName]\t[[$term getMTerm] getName]\t$routing"
  if {!$routing} {lappend disconnected [list $term [$term getNet]]; $term disconnect}
}}
close $f
set pg_terms {}
foreach lib [$db getLibs] {foreach master [$lib getMasters] {foreach term [$master getMTerms] {
  set type [$term getSigType]
  if {$type == "POWER" || $type == "GROUND"} {lappend pg_terms [list $term $type]; $term setSigType SIGNAL}
}}}
foreach name {VPWR VGND} {
  set net [$block findNet $name]
  $net setSigType SIGNAL
  foreach term [$net getBTerms] {$term setSigType SIGNAL; $term setIoType INPUT}
}
set out_net [$block findNet OUT]
if {[$out_net isSpecial]} {error "Unexpected preexisting OUT special status"}
$out_net setSpecial
@ADAPT_BUSES@
snapshot {@OUT@/adapted}
set f [open {@OUT@/proxy_shapes.tsv} w]
foreach name {__fixed_bus_selected __fixed_bus_VPWR __fixed_bus_VGND} {
  set term [$block findBTerm $name]
  foreach pin [$term getBPins] {foreach b [$pin getBoxes] {
    puts $f "$name\t[[$b getTechLayer] getName]\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"
  }}
}
close $f
write_db @OUT@/router_input.odb
# A future gated routing producer inserts routing commands here, then proves
# physical metal connectivity by streamed native LVS. This preflight routes none.
@ROUTING_BODY@
foreach pair $disconnected {lassign $pair term net; $term connect $net}
@RESTORE_BUSES@
foreach name {VPWR VGND} {
  set net [$block findNet $name]
  set type [expr {$name == "VPWR" ? "POWER" : "GROUND"}]
  $net setSigType $type
  foreach term [$net getBTerms] {$term setSigType $type; $term setIoType INOUT}
}
foreach pair $pg_terms {lassign $pair term type; $term setSigType $type}
$out_net clearSpecial
snapshot {@OUT@/after}
write_db @OUT@/restored.odb
exit
