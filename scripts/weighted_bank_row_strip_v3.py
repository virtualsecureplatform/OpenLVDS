# SPDX-License-Identifier: GPL-3.0-only
"""Keep the active control row and the original floorplan boundary rows."""
import weighted_bank_flow_v3 as flow


def control_box(spec,places,sizes):
    cells=[c for c in spec['cells'] if c['model'].startswith(flow.SC)]
    if len(cells)!=16 or set(places)!={c['name'] for c in cells}:
        raise ValueError('Require exactly the sixteen source controls')
    boxes=[]
    for c in cells:
        p=places[c['name']];size=sizes[c['model']];x,y=p['location']
        if p['orientation']!='N' or size['height']!=2.72:raise ValueError('Unexpected native control row')
        boxes.append([round(v*1000) for v in [x,y,x+size['width'],y+size['height']]])
    if len({(b[1],b[3]) for b in boxes})!=1:raise ValueError('Controls do not share one native row')
    return [min(b[0] for b in boxes),boxes[0][1],max(b[2] for b in boxes),boxes[0][3]]


def tcl(spec,box,report):
    x0,y0,x1,y1=box
    names=' '.join(c['name'] for c in spec['cells'])
    return f'''# Delete only generated physical tap instances and unused rows.
set strip_block [ord::get_db_block]
set strip_names {{{names}}}
proc strip_snapshot {{block names}} {{
  set result {{}}
  foreach name $names {{
    set inst [$block findInst $name]
    if {{$inst == "NULL"}} {{error "Original instance missing: $name"}}
    lappend result $name [[$inst getMaster] getName]
    foreach pin [$inst getITerms] {{
      set net [$pin getNet]
      if {{$net == "NULL"}} {{error "Original terminal disconnected"}}
      lappend result [[$pin getMTerm] getName] [$net getName]
    }}
  }}
  return $result
}}
set strip_before [strip_snapshot $strip_block $strip_names]
set strip_keep {{}}
foreach row [$strip_block getRows] {{
  set b [$row getBBox]
  if {{[$b yMin] == {y0} && [$b yMax] == {y1} && [$b xMin] <= {x0} && [$b xMax] >= {x1}}} {{
    lappend strip_keep $row
    set strip_left [$b xMin]
    set strip_right [$b xMax]
  }}
}}
if {{[llength $strip_keep] != 1}} {{error "No unique row contains every original control"}}
# Retain boundary rows so the detailed legalizer sees the full bank extent.
set strip_min_y 2147483647
set strip_max_y -2147483647
foreach row [$strip_block getRows] {{
  set b [$row getBBox]
  set strip_min_y [expr {{min($strip_min_y,[$b yMin])}}]
  set strip_max_y [expr {{max($strip_max_y,[$b yMin])}}]
}}
foreach row [$strip_block getRows] {{
  set b [$row getBBox]
  if {{([$b yMin] == $strip_min_y || [$b yMin] == $strip_max_y) && $row ni $strip_keep}} {{lappend strip_keep $row}}
}}
set strip_rows 0
foreach row [$strip_block getRows] {{
  if {{$row ni $strip_keep}} {{odb::dbRow_destroy $row; incr strip_rows}}
}}
set strip_taps 0
foreach inst [$strip_block getInsts] {{
  if {{[[$inst getMaster] getName] == "sky130_fd_sc_hd__tapvpwrvgnd_1"}} {{
    if {{[$inst getName] in $strip_names}} {{error "Cannot remove an original functional instance"}}
    set b [$inst getBBox]
    set strip_inside 0
    foreach row $strip_keep {{
      set rb [$row getBBox]
      if {{[$b yMin] == [$rb yMin] && [$b yMax] == [$rb yMax] && [$b xMin] >= [$rb xMin] && [$b xMax] <= [$rb xMax]}} {{set strip_inside 1}}
    }}
    if {{!$strip_inside}} {{
      odb::dbInst_destroy $inst
      incr strip_taps
    }}
  }}
}}
if {{[strip_snapshot $strip_block $strip_names] != $strip_before}} {{error "Row trimming changed the original circuit"}}
set strip_report [open {{{report}}} w]
puts $strip_report "rows_kept\\t[llength $strip_keep]"
puts $strip_report "rows_removed\\t$strip_rows"
puts $strip_report "taps_removed\\t$strip_taps"
puts $strip_report "row_bbox_dbu\\t$strip_left\\t{y0}\\t$strip_right\\t{y1}"
puts $strip_report "original_circuit_unchanged\\t1"
close $strip_report
'''
