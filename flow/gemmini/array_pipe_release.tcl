# POST_GLOBAL_PLACE hook: undo array_pipe_hold.tcl once global placement is done. The array blockage
# is removed and the pipeline registers become movable again, so the resizer, detailed placement and
# clock tree synthesis can use the channels (the array's clock buffers belong there).
set block [ord::get_db_block]
set nb 0
foreach bl [$block getBlockages] { if {[$bl getInstance] == "NULL"} { odb::dbBlockage_destroy $bl; incr nb } }
set n 0
foreach inst [$block getInsts] {
  if {[$inst getPlacementStatus] eq "FIRM" && [string match "ex_controller/mesh/mesh/*" [$inst getName]]} {
    $inst setPlacementStatus PLACED; incr n
  }
}
puts "array_pipe_release: $nb blockage(s) removed, $n pipeline cells released"
