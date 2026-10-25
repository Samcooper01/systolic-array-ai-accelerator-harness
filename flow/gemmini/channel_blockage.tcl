# Runs after tap-cell insertion (POST_TAPCELL_TCL). Keeps standard cells out of the 60 um channel
# between the Scratchpad and the ExecuteController, so the channel carries only the 3,504-bit
# interface. Tap-cell insertion leaves a short row segment in the channel for every row (with an
# endcap at each end); those segments are removed with their endcaps and taps, so nothing can be
# placed there. (A placement blockage does not work: the endcaps would sit inside it.)
proc size_of {inst_name} {
  set m [[[ord::get_db_block] findInst $inst_name] getMaster]
  return [list [ord::dbu_to_microns [$m getWidth]] [ord::dbu_to_microns [$m getHeight]]]
}
set margin 20.0
set gap 60.0
lassign [size_of spad] sw sh
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set cx1 [expr {int(($margin + $sw) * $dbu)}]
set cx2 [expr {int(($margin + $sw + $gap) * $dbu)}]
set rows 0; set cells 0
foreach row [$block getRows] {
  set bb [$row getBBox]
  if { [$bb xMin] >= $cx1 && [$bb xMax] <= $cx2 } {
    foreach inst [$block getInsts] { break }
    set rows [expr {$rows + 1}]
    set rb $bb
    lappend dead [list [$bb xMin] [$bb yMin] [$bb xMax] [$bb yMax]]
    odb::dbRow_destroy $row
  }
}
# remove the physical-only cells (endcaps, taps) that sat on the removed segments
foreach inst [$block getInsts] {
  if { ![[$inst getMaster] isCore] } { continue }
  set ib [$inst getBBox]
  if { [$ib xMin] >= $cx1 && [$ib xMax] <= $cx2 && [string match "PHY_*" [$inst getName]] || ([$ib xMin] >= $cx1 && [$ib xMax] <= $cx2 && [string match "TAP_*" [$inst getName]]) } {
    odb::dbInst_destroy $inst; incr cells
  }
}
puts "channel_blockage: removed $rows row segments and $cells endcap/tap cells between x [expr {$cx1/$dbu}] and [expr {$cx2/$dbu}]"
