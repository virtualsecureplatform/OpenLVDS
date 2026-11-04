# Delete only generated physical tap instances and unused rows.
set strip_block [ord::get_db_block]
set strip_names {tie coarse_buffer0 forward0 turn0 pass0 merge0 coarse_buffer1 forward1 turn1 pass1 merge1 coarse_buffer2 forward2 turn2 pass2 merge2 coarse_buffer3 forward3 turn3 pass3 merge3 coarse_buffer4 forward4 turn4 pass4 merge4 coarse_buffer5 forward5 turn5 pass5 merge5 coarse_buffer6 forward6 turn6 pass6 merge6 coarse_buffer7 forward7 turn7 pass7 merge7 coarse_buffer8 forward8 turn8 pass8 merge8 coarse_buffer9 forward9 turn9 pass9 merge9 coarse_buffer10 forward10 turn10 pass10 merge10 coarse_buffer11 forward11 turn11 pass11 merge11 coarse_buffer12 forward12 turn12 pass12 merge12 coarse_buffer13 forward13 turn13 pass13 merge13 coarse_buffer14 forward14 turn14 pass14 merge14 turn15 merge15 fine_buffer0 fine_inverse0 fine0 fine_buffer1 fine_inverse1 fine1 fine_buffer2 fine_inverse2 fine2 fine_buffer3 fine_inverse3 fine3 fine_buffer4 fine_inverse4 fine4 shared_base}
proc strip_snapshot {block names} {
  set result {}
  foreach name $names {
    set inst [$block findInst $name]
    if {$inst == "NULL"} {error "Original instance missing: $name"}
    lappend result $name [[$inst getMaster] getName]
    foreach pin [$inst getITerms] {
      set net [$pin getNet]
      if {$net == "NULL"} {error "Original terminal disconnected"}
      lappend result [[$pin getMTerm] getName] [$net getName]
    }
  }
  return $result
}
set strip_before [strip_snapshot $strip_block $strip_names]
set strip_keep {}
foreach row [$strip_block getRows] {
  set b [$row getBBox]
  if {[$b yMin] == 296480 && [$b yMax] == 299200 && [$b xMin] <= 209760 && [$b xMax] >= 266340} {
    lappend strip_keep $row
    set strip_left [$b xMin]
    set strip_right [$b xMax]
  }
}
if {[llength $strip_keep] != 1} {error "No unique row contains every original control"}
# Retain boundary rows so the detailed legalizer sees the full bank extent.
set strip_min_y 2147483647
set strip_max_y -2147483647
foreach row [$strip_block getRows] {
  set b [$row getBBox]
  set strip_min_y [expr {min($strip_min_y,[$b yMin])}]
  set strip_max_y [expr {max($strip_max_y,[$b yMin])}]
}
foreach row [$strip_block getRows] {
  set b [$row getBBox]
  if {([$b yMin] == $strip_min_y || [$b yMin] == $strip_max_y) && $row ni $strip_keep} {lappend strip_keep $row}
}
set strip_rows 0
foreach row [$strip_block getRows] {
  if {$row ni $strip_keep} {odb::dbRow_destroy $row; incr strip_rows}
}
set strip_taps 0
foreach inst [$strip_block getInsts] {
  if {[[$inst getMaster] getName] == "sky130_fd_sc_hd__tapvpwrvgnd_1"} {
    if {[$inst getName] in $strip_names} {error "Cannot remove an original functional instance"}
    set b [$inst getBBox]
    set strip_inside 0
    foreach row $strip_keep {
      set rb [$row getBBox]
      if {[$b yMin] == [$rb yMin] && [$b yMax] == [$rb yMax] && [$b xMin] >= [$rb xMin] && [$b xMax] <= [$rb xMax]} {set strip_inside 1}
    }
    if {!$strip_inside} {
      odb::dbInst_destroy $inst
      incr strip_taps
    }
  }
}
if {[strip_snapshot $strip_block $strip_names] != $strip_before} {error "Row trimming changed the original circuit"}
set strip_report [open {weighted-bank-active-rows.tsv} w]
puts $strip_report "rows_kept\t[llength $strip_keep]"
puts $strip_report "rows_removed\t$strip_rows"
puts $strip_report "taps_removed\t$strip_taps"
puts $strip_report "row_bbox_dbu\t$strip_left\t296480\t$strip_right\t299200"
puts $strip_report "original_circuit_unchanged\t1"
close $strip_report
source /work/OpenLVDS/constraints/v2/weighted_bank_pdn_v13.tcl
