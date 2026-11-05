# SPDX-License-Identifier: GPL-3.0-only
"""Use sparse powered rows during PDN, then restore all placement metadata and block unpowered placement sites."""
import weighted_bank_row_strip_v3 as previous
control_box=previous.control_box


def tcl(spec,box,report):
    capture='''global bank_original_rows bank_original_sites strip_block strip_names strip_before
# Capture exact placement-only row metadata before power-grid preparation.
proc bank_row_signature {row} {
  set b [$row getBBox]
  return [list [$row getName] [[$row getSite] getName] {*}[$row getOrigin] [$row getOrient] [$row getDirection] [$row getSiteCount] [$row getSpacing] [$b xMin] [$b yMin] [$b xMax] [$b yMax]]
}
set bank_original_rows {}
set bank_original_sites {}
foreach row [[ord::get_db_block] getRows] {
  lappend bank_original_rows [bank_row_signature $row]
  dict set bank_original_sites [[$row getSite] getName] [$row getSite]
}
'''
    restore='''# LibreLane has no post-PDN hook: use a single-use Tcl leave callback.
# It runs only after successful generation, before write_views and checks.
proc bank_restore_rows_after_pdn {command code result operation} {
  if {$code != 0} {return}
  foreach flag {-check_only -report_only -reset -ripup} {
    if {[lsearch -exact $command $flag] >= 0} {return}
  }
  trace remove execution pdngen leave bank_restore_rows_after_pdn
  global bank_original_rows bank_original_sites strip_block strip_names strip_before
  set inst_count [llength [$strip_block getInsts]]
  set surviving {}
  foreach row [$strip_block getRows] {lappend surviving [$row getName]}
  set restored 0
  set blocked 0
  foreach definition $bank_original_rows {
    lassign $definition name site x y orient direction count spacing bx0 by0 bx1 by1
    if {[lsearch -exact $surviving $name] < 0} {
      odb::dbRow_create $strip_block $name [dict get $bank_original_sites $site] $x $y $orient $direction $count $spacing
      # Retain the row for legalizer geometry, but it has no generated rails.
      # A hard placement blockage keeps subsequent diodes/fillers off it.
      set blockage [odb::dbBlockage_create $strip_block $bx0 $by0 $bx1 $by1]
      if {[$blockage isSoft]} {error "Unpowered row blockage must be hard"}
      incr blocked
      lappend surviving $name
      incr restored
    }
  }
  set observed {}
  foreach row [$strip_block getRows] {lappend observed [bank_row_signature $row]}
  if {[lsort $observed] != [lsort $bank_original_rows]} {error "Original row metadata not restored exactly"}
  if {[llength [$strip_block getInsts]] != $inst_count || [strip_snapshot $strip_block $strip_names] != $strip_before} {
    error "Row restoration changed actual cell instances or original circuit"
  }
  set f [open @REPORT@ w]
  puts $f "rows_restored\\t$restored"
  puts $f "unpowered_row_blockages\\t$blocked"
  puts $f "rows_final\\t[llength $observed]"
  puts $f "exact_row_metadata_passed\\t1"
  puts $f "original_circuit_unchanged\\t1"
  puts $f "instance_count_unchanged\\t1"
  close $f
}
trace add execution pdngen leave bank_restore_rows_after_pdn
'''
    return capture+previous.tcl(spec,box,report)+restore.replace('@REPORT@','{'+str(report)+'.restored.tsv}')
